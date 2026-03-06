"""
Betcris (be.betcris.do) scraper.
Uses Playwright to:
  1. Log in with credentials
  2. Intercept internal API/XHR calls that load odds
  3. Extract and normalize odds data
"""
import os
import json
import asyncio
from datetime import datetime
from typing import Optional
from loguru import logger

from .base_scraper import BaseScraper, OddsData, american_to_decimal


# Sports to navigate to on Betcris
BETCRIS_SPORTS = [
    ("NBA",   "basketball/nba",             "NBA"),
    ("NCAAB", "basketball/ncaa-basketball", "NCAA Basketball"),
    ("NFL",   "football/nfl",               "NFL"),
    ("NCAAF", "football/ncaa-football",     "NCAA Football"),
    ("MLB",   "baseball/mlb",               "MLB"),
    ("NHL",   "hockey/nhl",                 "NHL"),
    ("EUROL", "basketball/euroleague",      "EuroLiga"),
    ("SOC",   "soccer/champions-league",    "Champions League"),
]

BASE_URL = os.getenv("BETCRIS_URL", "https://be.betcris.do")

# Map Betcris internal idSport codes → our sport_code convention
BETCRIS_SPORT_MAP = {
    "NBA":  "NBA",
    "CBB":  "NCAAB",   # College Basketball
    "NFL":  "NFL",
    "CFB":  "NCAAF",   # College Football
    "MLB":  "MLB",
    "NHL":  "NHL",
    "SOC":  "SOC",
    "EUR":  "EUROL",
}
USERNAME = os.getenv("BETCRIS_USERNAME", "")
PASSWORD = os.getenv("BETCRIS_PASSWORD", "")

# Cached cookies — reused across scrape cycles
_session_cookies: list = []


def _build_playwright_proxy() -> dict | None:
    """Parse PROXY_URL into Playwright proxy config with separate auth fields."""
    raw = os.getenv("PROXY_URL", "").strip()
    if not raw:
        return None
    from urllib.parse import urlparse
    p = urlparse(raw)
    config = {"server": f"{p.scheme}://{p.hostname}:{p.port}"}
    if p.username:
        config["username"] = p.username
    if p.password:
        config["password"] = p.password
    return config


class BetcrisScraper(BaseScraper):
    """Playwright-based scraper for Betcris Dominican Republic."""

    def __init__(self):
        super().__init__("Betcris", BASE_URL)

    # ------------------------------------------------------------------ #
    #  Public entry point                                                  #
    # ------------------------------------------------------------------ #
    async def scrape(self) -> list[OddsData]:
        """Scrape NCAA + NBA (+ other sports) from Betcris."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.logger.error(
                "Playwright not installed. Run: "
                "pip install playwright && playwright install chromium"
            )
            return []

        all_odds: list[OddsData] = []

        proxy_config = _build_playwright_proxy()

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
                proxy=proxy_config,
            )
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
            )

            # Restore saved cookies
            global _session_cookies
            if _session_cookies:
                await context.add_cookies(_session_cookies)

            page = await context.new_page()

            # Collect intercepted API responses
            intercepted: list[dict] = []
            page.on("response", lambda r: asyncio.ensure_future(
                _intercept_response(r, intercepted)
            ))

            # Login
            logged_in = await self._ensure_login(page, context)
            if not logged_in:
                self.logger.error("Betcris: login failed")
                await browser.close()
                return []

            # Scrape each sport
            for sport_code, url_slug, league in BETCRIS_SPORTS:
                try:
                    intercepted.clear()
                    odds = await self._scrape_sport(
                        page, sport_code, url_slug, league, intercepted
                    )
                    all_odds.extend(odds)
                    self.logger.info(f"Betcris {sport_code}: {len(odds)} odds")
                except Exception as e:
                    self.logger.error(f"Betcris {sport_code} error: {e}")

            _session_cookies = await context.cookies()
            await browser.close()

        return all_odds

    # ------------------------------------------------------------------ #
    #  Login                                                               #
    # ------------------------------------------------------------------ #
    async def _ensure_login(self, page, context) -> bool:
        """Login to Betcris. Returns True on success."""
        global _session_cookies

        # Check if already logged in by navigating to sports and checking URL
        try:
            await page.goto(f"{BASE_URL}/en/sports", timeout=60000,
                            wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            if "/front/login" not in page.url:
                self.logger.info("Betcris: session still valid")
                return True
        except Exception:
            pass

        self.logger.info("Betcris: starting login...")

        try:
            # Navigate directly to the Betcris login page
            await page.goto(f"{BASE_URL}/front/login", timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)  # let the SPA render

            # If SPA redirected us away, we're already logged in
            if "/front/login" not in page.url:
                self.logger.info(f"Betcris: already logged in (at {page.url})")
                _session_cookies = await context.cookies()
                return True

            # Wait for the accountId field to appear
            await page.wait_for_function(
                "document.querySelector(\"input[name='accountId']\") !== null",
                timeout=30000,
            )

            # Use JavaScript injection to set values and fire events
            # (Playwright fill() doesn't trigger the SPA's internal validators)
            await page.evaluate(f"""
                var u = document.querySelector("input[name='accountId']");
                var p = document.querySelector("input[name='password']");
                if (u) {{
                    u.value = {repr(USERNAME)};
                    u.dispatchEvent(new Event('input', {{bubbles:true}}));
                    u.dispatchEvent(new Event('change', {{bubbles:true}}));
                }}
                if (p) {{
                    p.value = {repr(PASSWORD)};
                    p.dispatchEvent(new Event('input', {{bubbles:true}}));
                    p.dispatchEvent(new Event('change', {{bubbles:true}}));
                }}
            """)

            # Click the Entrar (submit) button
            await page.click("button:has-text('Entrar')", timeout=30000)

            # Wait for redirect away from the login page
            try:
                await page.wait_for_url(
                    lambda url: "/front/login" not in url,
                    timeout=30000,
                )
            except Exception:
                await page.wait_for_load_state("domcontentloaded", timeout=30000)

            self.logger.info(f"Betcris: post-login URL = {page.url}")
            _session_cookies = await context.cookies()
            return True

        except Exception as e:
            self.logger.error(f"Betcris login exception: {e}")
            return False

    # ------------------------------------------------------------------ #
    #  Scrape one sport                                                    #
    # ------------------------------------------------------------------ #
    async def _scrape_sport(
        self,
        page,
        sport_code: str,
        url_slug: str,
        league: str,
        intercepted: list[dict],
    ) -> list[OddsData]:

        urls = [
            f"{BASE_URL}/en/sports/{url_slug}",
            f"{BASE_URL}/en/sports/lines/{url_slug}",
        ]

        for url in urls:
            try:
                await page.goto(url, timeout=60000, wait_until="domcontentloaded")
                await page.wait_for_timeout(5000)  # Wait for JS to render

                # Try intercepted API data first (most reliable)
                odds = self._parse_intercepted(intercepted, sport_code, league)
                if odds:
                    return odds

                # Fallback: DOM scraping
                odds = await self._scrape_dom(page, sport_code, league)
                if odds:
                    return odds

            except Exception as e:
                self.logger.warning(f"Betcris {url}: {e}")

        return []

    # ------------------------------------------------------------------ #
    #  Parse intercepted XHR/fetch API responses                          #
    # ------------------------------------------------------------------ #
    def _parse_intercepted(
        self, intercepted: list[dict], sport_code: str, league: str
    ) -> list[OddsData]:
        results = []
        for resp in intercepted:
            try:
                url = resp.get("url", "")
                raw = resp.get("body", "")
                data = json.loads(raw) if isinstance(raw, str) else raw

                # Both schedule endpoints use _parse_betcris_schedule:
                # - scheduleGetCategoryContent: sport-specific (groups[].games[])
                # - scheduleGetMostPopular: cross-sport (Data.{UUID}), uses idSport per game
                if "scheduleGetCategoryContent" in url or "scheduleGetMostPopular" in url:
                    parsed = self._parse_betcris_schedule(data, sport_code, league)
                    if parsed:
                        results.extend(parsed)
                    continue  # don't also run _extract_from_json on same response

                # Generic JSON fallback for other endpoints
                results.extend(self._extract_from_json(data, sport_code, league))
            except Exception:
                continue
        return results

    def _parse_betcris_schedule(self, data, sport_code: str, league: str) -> list[OddsData]:
        """Parse two Betcris schedule API formats:

        Format A (scheduleGetMostPopular):
          data["Data"] = { UUID: { contenders, lines.ml, idSport } }

        Format B (scheduleGetCategoryContent):
          data["groups"] = [ { games: [ { contenders, lines.ml } ] } ]
        """
        results = []

        # Format B: scheduleGetCategoryContent  → groups[].games[]
        # Each game has idSport (NBA, CBB=NCAAB, etc.) — use it for correct tagging
        if "groups" in data:
            for group in data.get("groups", []):
                for game in group.get("games", []):
                    results.extend(self._parse_one_betcris_game(game, sport_code, league, use_game_sport=True))
            return results

        # Format A: scheduleGetMostPopular → Data.{UUID}
        games = data.get("Data") or data.get("data") or {}
        if not isinstance(games, dict):
            return results

        for game in games.values():
            if not isinstance(game, dict):
                continue
            contenders = game.get("contenders", [])
            if len(contenders) < 2:
                continue
            results.extend(self._parse_one_betcris_game(game, sport_code, league, use_game_sport=True))

        return results

    def _parse_one_betcris_game(
        self, game: dict, sport_code: str, league: str, use_game_sport: bool
    ) -> list[OddsData]:
        """Parse a single Betcris game node (used by both schedule formats)."""
        if not isinstance(game, dict):
            return []
        contenders = game.get("contenders", [])
        if len(contenders) < 2:
            return []
        away_team = contenders[0].get("name", "")
        home_team = contenders[1].get("name", "")
        if not away_team or not home_team:
            return []

        lines = game.get("lines", {})
        ml = lines.get("ml", {})
        away_dec = ml.get("vd")
        home_dec = ml.get("hd")
        if not away_dec or not home_dec:
            return []
        try:
            away_dec = float(away_dec)
            home_dec = float(home_dec)
        except (TypeError, ValueError):
            return []
        if away_dec <= 1.0 or home_dec <= 1.0:
            return []

        event_date = None
        try:
            from datetime import datetime
            ts = game.get("startTime", "") or game.get("eventdate", "")
            if ts:
                event_date = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except Exception:
            pass

        # Resolve sport code: prefer the game's own idSport (both endpoints have it),
        # mapping from Betcris internal codes (CBB→NCAAB, etc.) to our conventions.
        raw_sport = game.get("idSport", "")
        game_sport = BETCRIS_SPORT_MAP.get(raw_sport, raw_sport) if raw_sport else sport_code

        return [
            OddsData(
                bookmaker="Betcris", sport_code=game_sport, league=league,
                home_team=home_team, away_team=away_team, event_date=event_date,
                market_type="moneyline", outcome="home",
                odds_value=home_dec, raw_odds=str(ml.get("h", "")),
            ),
            OddsData(
                bookmaker="Betcris", sport_code=game_sport, league=league,
                home_team=home_team, away_team=away_team, event_date=event_date,
                market_type="moneyline", outcome="away",
                odds_value=away_dec, raw_odds=str(ml.get("v", "")),
            ),
        ]

    def _extract_from_json(self, data, sport_code: str, league: str) -> list[OddsData]:
        """Recursively find events with home/away odds in any JSON shape."""
        results = []

        if isinstance(data, list):
            for item in data:
                results.extend(self._extract_from_json(item, sport_code, league))
            return results

        if not isinstance(data, dict):
            return results

        # Detect an event node
        home = (data.get("home") or data.get("homeTeam") or
                data.get("home_team") or data.get("localTeam") or "")
        away = (data.get("away") or data.get("awayTeam") or
                data.get("away_team") or data.get("visitorTeam") or "")

        if home and away:
            for ml_key in ["moneyline", "ml", "money_line", "h2h", "odds"]:
                ml = data.get(ml_key)
                if not isinstance(ml, dict):
                    continue
                for outcome_key, outcome_label, team_name in [
                    ("home", "home", home),
                    ("1",    "home", home),
                    ("away", "away", away),
                    ("2",    "away", away),
                ]:
                    raw = ml.get(outcome_key)
                    val = self._to_decimal(raw)
                    if val:
                        results.append(OddsData(
                            bookmaker="Betcris",
                            sport_code=sport_code,
                            league=league,
                            home_team=str(home),
                            away_team=str(away),
                            event_date=self._parse_date(data),
                            market_type="moneyline",
                            outcome=outcome_label,
                            odds_value=val,
                            raw_odds=str(raw),
                        ))

        # Recurse into common collection keys
        for key in ["events", "games", "matches", "data", "results",
                    "lines", "markets", "items", "fixtures", "list"]:
            child = data.get(key)
            if isinstance(child, (list, dict)):
                results.extend(self._extract_from_json(child, sport_code, league))

        return results

    # ------------------------------------------------------------------ #
    #  DOM fallback                                                        #
    # ------------------------------------------------------------------ #
    async def _scrape_dom(
        self, page, sport_code: str, league: str
    ) -> list[OddsData]:
        results = []

        try:
            await page.wait_for_selector(
                "[class*='odds'], [class*='price'], [data-odds]", timeout=6000
            )
        except Exception:
            pass

        for sel in [".event-row", ".game-row", "[class*='event']", "[class*='game']"]:
            events = await page.query_selector_all(sel)
            for event in events:
                try:
                    parsed = await self._parse_dom_event(event, sport_code, league)
                    results.extend(parsed)
                except Exception:
                    continue
            if results:
                break

        return results

    async def _parse_dom_event(self, element, sport_code: str, league: str) -> list[OddsData]:
        results = []

        team_els = await element.query_selector_all(
            ".team-name, .competitor, [class*='team'], [class*='competitor']"
        )
        teams = [await el.inner_text() for el in team_els[:2]]
        if len(teams) < 2:
            return results

        home_team = teams[0].strip()
        away_team = teams[1].strip()

        odds_els = await element.query_selector_all(
            "[class*='odds'], [class*='price'], [data-odds]"
        )
        for i, el in enumerate(odds_els[:2]):
            text = (await el.inner_text()).strip()
            val = self._to_decimal(text)
            if val:
                results.append(OddsData(
                    bookmaker="Betcris",
                    sport_code=sport_code,
                    league=league,
                    home_team=home_team,
                    away_team=away_team,
                    event_date=None,
                    market_type="moneyline",
                    outcome="home" if i == 0 else "away",
                    odds_value=val,
                    raw_odds=text,
                ))
        return results

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #
    def _to_decimal(self, raw) -> Optional[float]:
        if raw is None:
            return None
        s = str(raw).strip()
        if s.lstrip("+-").replace(".", "").isdigit():
            if s.startswith(("+", "-")) and not "." in s:
                return american_to_decimal(s)
            try:
                val = float(s)
                if 1.01 <= val <= 100.0:
                    return val
            except ValueError:
                pass
        return None

    def _parse_date(self, data: dict) -> Optional[datetime]:
        for key in ["date", "startDate", "start_date", "eventDate", "kickoff"]:
            val = data.get(key)
            if val:
                try:
                    return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
                except Exception:
                    pass
        return None


# ------------------------------------------------------------------ #
#  Network response interceptor                                        #
# ------------------------------------------------------------------ #
async def _intercept_response(response, intercepted: list):
    """Capture JSON from Betcris backend API calls."""
    try:
        url = response.url
        ct = response.headers.get("content-type", "")

        if "betcris" not in url:
            return
        if "json" not in ct:
            return
        if response.status != 200:
            return

        body = await response.text()
        if 50 < len(body) < 2_000_000:
            intercepted.append({"url": url, "body": body})
            logger.debug(f"Betcris API captured: {url[:100]}")

    except Exception:
        pass
