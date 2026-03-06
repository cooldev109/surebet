"""
JuancitoSport (juancitosport.com.do) scraper.
Uses Playwright to:
  1. Login at /acceso (user/passw fields)
  2. Navigate to /deportes/ which embeds a BOSS Wagering iframe
  3. Click each sport in the sidebar, scrape game rows from the iframe
"""
import os
import re
import asyncio
from datetime import datetime
from typing import Optional
from bs4 import BeautifulSoup
from loguru import logger

from .base_scraper import BaseScraper, OddsData, american_to_decimal


BASE_URL = os.getenv("JUANCITO_URL", "https://www.juancitosport.com.do")
USERNAME = os.getenv("JUANCITO_USERNAME", "")
PASSWORD = os.getenv("JUANCITO_PASSWORD", "")

# Sports to click in the BOSS Wagering sidebar
# (label shown in sidebar, sport_code, league name)
SPORTS_TO_SCRAPE = [
    ("NBA",          "NBA",   "NBA"),
    ("NCAA BASKET",  "NCAAB", "NCAA Basketball"),
    ("COLLEGE BASEBALL", "MLB", "College Baseball"),
]

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


class JuancitoScraper(BaseScraper):
    """Playwright-based scraper for JuancitoSport (BOSS Wagering iframe)."""

    def __init__(self):
        super().__init__("JuancitoSport", BASE_URL)

    async def scrape(self) -> list[OddsData]:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            self.logger.error("Playwright not installed.")
            return []

        all_odds: list[OddsData] = []

        # JuancitoSport is accessible from Philippines directly — no proxy needed
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )

            global _session_cookies
            if _session_cookies:
                await context.add_cookies(_session_cookies)

            page = await context.new_page()

            # Login
            logged_in = await self._login(page, context)
            if not logged_in:
                self.logger.error("JuancitoSport: login failed")
                await browser.close()
                return []

            # Navigate to sports page (loads BOSS iframe)
            await page.goto(f"{BASE_URL}/deportes/", timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)

            # Find the BOSS Wagering sports iframe
            sports_frame = self._get_sports_frame(page)
            if not sports_frame:
                self.logger.error("JuancitoSport: sports iframe not found")
                await browser.close()
                return []

            self.logger.info(f"JuancitoSport: sports iframe found")

            # Scrape each sport
            for sidebar_label, sport_code, league in SPORTS_TO_SCRAPE:
                try:
                    odds = await self._scrape_sport(
                        page, sports_frame, sidebar_label, sport_code, league
                    )
                    all_odds.extend(odds)
                    self.logger.info(f"JuancitoSport {sport_code}: {len(odds)} odds")
                except Exception as e:
                    self.logger.error(f"JuancitoSport {sport_code}: {e}")

            _session_cookies = await context.cookies()
            await browser.close()

        return all_odds

    # ------------------------------------------------------------------ #
    #  Login                                                               #
    # ------------------------------------------------------------------ #
    async def _login(self, page, context) -> bool:
        global _session_cookies

        # Only check existing session if we have saved cookies from a previous run
        if _session_cookies:
            try:
                await page.goto(f"{BASE_URL}/deportes/", timeout=60000, wait_until="domcontentloaded")
                balance = await page.query_selector(".account-balance, text=RD$")
                if balance:
                    self.logger.info("JuancitoSport: session still valid, skipping login")
                    return True
            except Exception:
                pass
            self.logger.info("JuancitoSport: session expired, re-logging in...")
        else:
            self.logger.info("JuancitoSport: logging in...")

        try:
            await page.goto(f"{BASE_URL}/acceso", timeout=60000, wait_until="domcontentloaded")

            # Wait for form elements to appear in DOM (page has 3 login forms)
            await page.wait_for_function(
                "document.querySelector('input[name=\"user\"]') !== null",
                timeout=60000,
            )

            # Use JavaScript to fill and submit — bypasses visibility/overlay issues
            await page.evaluate(f"""
                var u = document.querySelector('#user_login') || document.querySelector('input[name="user"]');
                var p = document.querySelector('#user_pass') || document.querySelector('input[name="passw"]');
                if (u) u.value = {repr(USERNAME)};
                if (p) p.value = {repr(PASSWORD)};
            """)

            # Trigger native input events so the form recognises the values
            await page.evaluate("""
                ['user_login','user_pass'].forEach(function(id) {
                    var el = document.getElementById(id);
                    if (el) {
                        el.dispatchEvent(new Event('input', {bubbles:true}));
                        el.dispatchEvent(new Event('change', {bubbles:true}));
                    }
                });
            """)

            # Submit via the wp-submit button or first Ingresar button
            await page.evaluate("""
                var btn = document.getElementById('wp-submit');
                if (!btn) {
                    var btns = document.querySelectorAll('button,input[type=submit]');
                    for (var b of btns) {
                        if ((b.value||b.textContent||'').toLowerCase().includes('ingresar')) { btn = b; break; }
                    }
                }
                if (btn) btn.click();
            """)

            # Wait up to 30s for redirect away from /acceso
            try:
                await page.wait_for_url(
                    lambda url: "/acceso" not in url,
                    timeout=30000,
                )
            except Exception:
                await page.wait_for_load_state("domcontentloaded", timeout=30000)

            self.logger.info(f"JuancitoSport: post-login URL = {page.url}")
            _session_cookies = await context.cookies()
            return True

        except Exception as e:
            self.logger.error(f"JuancitoSport login error: {e}")
            return False

    # ------------------------------------------------------------------ #
    #  Find sports iframe                                                  #
    # ------------------------------------------------------------------ #
    def _get_sports_frame(self, page):
        for frame in page.frames:
            if "deportes.juancitosport" in frame.url:
                return frame
        return None

    # ------------------------------------------------------------------ #
    #  Scrape one sport from sidebar                                       #
    # ------------------------------------------------------------------ #
    async def _scrape_sport(
        self, page, frame, sidebar_label: str, sport_code: str, league: str
    ) -> list[OddsData]:
        try:
            # Click the sport in the BOSS sidebar (5s timeout — sport may not be in menu)
            sport_link = frame.locator(f"text={sidebar_label}").first
            await sport_link.click(timeout=5000)
            await page.wait_for_timeout(3000)
        except Exception as e:
            self.logger.debug(f"JuancitoSport: '{sidebar_label}' not available: {e}")
            return []

        # Parse visible text from the iframe
        try:
            html = await frame.content()
            return self._parse_boss_html(html, sport_code, league, sidebar_label)
        except Exception as e:
            self.logger.error(f"JuancitoSport parse error: {e}")
            return []

    # ------------------------------------------------------------------ #
    #  Parse BOSS Wagering HTML                                            #
    # ------------------------------------------------------------------ #
    def _parse_boss_html(
        self, html: str, sport_code: str, league: str, sidebar_label: str = ""
    ) -> list[OddsData]:
        """
        Parse the BOSS Wagering HTML.

        Main game table format (two consecutive <tr> rows per game):
          Away row: Team  spread  juice  [ML]  O/U  juice
          Home row: Team  spread  juice  [ML]  O/U  juice

        BOSS Wagering also renders a "Próximos eventos" sidebar that lists
        upcoming games from ALL sports (including soccer), each sport section
        preceded by a <div class="colSubHeader">SPORT NAME</div> marker.

        We use those markers to identify and EXCLUDE sidebar rows that belong
        to sports other than `sidebar_label`, preventing cross-sport row
        contamination (e.g., soccer rows appearing in NBA results).
        """
        soup = BeautifulSoup(html, "lxml")
        results = []

        # --- Build set of TR elements to exclude (sidebar rows for other sports) ---
        excluded_tr_ids: set[int] = set()
        target_upper = sidebar_label.upper() if sidebar_label else ""

        for header in soup.find_all(class_="colSubHeader"):
            header_text = header.get_text(" ", strip=True).upper()
            # Skip if this section matches our target sport
            if target_upper and target_upper in header_text:
                continue
            # Walk forward to find the next <table> sibling — that's the section table
            sib = header.find_next_sibling()
            while sib:
                tag = getattr(sib, "name", None)
                if tag == "table":
                    for tr in sib.find_all("tr"):
                        excluded_tr_ids.add(id(tr))
                    break
                # Stop at the next section header
                classes = sib.get("class", []) if hasattr(sib, "get") else []
                if "colSubHeader" in classes:
                    break
                sib = sib.find_next_sibling()

        # --- Collect candidate rows, skipping excluded sidebar rows ---
        all_rows = soup.find_all("tr")
        game_rows = []

        for row in all_rows:
            if id(row) in excluded_tr_ids:
                continue
            text = row.get_text(" ", strip=True)
            if re.search(r"[+-]\d{3}", text) and len(text) > 15:
                cells = [td.get_text(" ", strip=True) for td in row.find_all(["td", "th"])]
                if cells:
                    game_rows.append({"text": text, "cells": cells})

        # Remove duplicate rows (BOSS renders the same row in nested tables)
        seen = set()
        unique_rows = []
        for gr in game_rows:
            key = gr["text"][:80]
            if key not in seen:
                seen.add(key)
                unique_rows.append(gr)

        # Process consecutive pairs: BOSS Wagering lists visiting team first,
        # home team second. We no longer rely on a trailing '@' because newer
        # BOSS versions omit it. Instead we just walk the rows two at a time.
        i = 0
        while i < len(unique_rows) - 1:
            row1 = unique_rows[i]
            row2 = unique_rows[i + 1]

            game = self._extract_game(row1, row2, sport_code, league)
            if game:
                results.extend(game)
                i += 2
            else:
                i += 1

        return results

    def _extract_game(
        self, row1: dict, row2: dict, sport_code: str, league: str
    ) -> list[OddsData]:
        """Extract a complete game (home + away odds) from two consecutive rows."""

        team1, ml1 = self._extract_team_and_ml(row1["text"])
        team2, ml2 = self._extract_team_and_ml(row2["text"])

        if not team1 or not team2 or not ml1 or not ml2:
            return []

        val1 = american_to_decimal(ml1)
        val2 = american_to_decimal(ml2)

        if not val1 or not val2:
            return []

        # In BOSS Wagering: row1 = away (visiting) team, row2 = home team.
        # The '@' symbol used to appear at the end of row1 but newer BOSS
        # versions omit it. We now treat row1 as away unconditionally.
        away_team, away_val, away_raw = team1, val1, ml1
        home_team, home_val, home_raw = team2, val2, ml2

        return [
            OddsData(
                bookmaker="JuancitoSport",
                sport_code=sport_code, league=league,
                home_team=home_team, away_team=away_team,
                event_date=None, market_type="moneyline",
                outcome="home", odds_value=home_val, raw_odds=home_raw,
            ),
            OddsData(
                bookmaker="JuancitoSport",
                sport_code=sport_code, league=league,
                home_team=home_team, away_team=away_team,
                event_date=None, market_type="moneyline",
                outcome="away", odds_value=away_val, raw_odds=away_raw,
            ),
        ]

    def _extract_team_and_ml(self, row_text: str) -> tuple[Optional[str], Optional[str]]:
        r"""
        From a BOSS row like:
          'Boston Celtics -6 -110 -235 O 211½ -110 @'
        Extract:
          team = 'Boston Celtics'
          ml   = '-235'  (the moneyline, not the spread or juice)

        Strategy: spreads are 1-2 digit values (ignored by \d{3,4}).
        Among the 3+ digit values, the moneyline deviates most from -110 juice.
        If all 3-digit values are close to -110 (no explicit ML), we fall back
        to the first 3-digit value as a proxy.
        """
        # Only consider 3+ digit American odds (excludes spreads like -6, +11)
        odds_found = re.findall(r"[+-]\d{3,4}", row_text)

        if not odds_found:
            return None, None

        # Pick the value that deviates most from standard -110 juice.
        # When an explicit ML is present (e.g., -235, +190) it will have the
        # largest deviation. When only juice is present, we fall back to the
        # first value found.
        ml = max(odds_found, key=lambda x: abs(int(x) + 110))

        # Extract team name: everything before the first +/- sign
        team_match = re.match(r"^([A-Za-z][A-Za-z\s\.]+?)(?=\s*[+-]\d)", row_text.strip())
        team = team_match.group(1).strip() if team_match else None

        if team:
            team = re.sub(r"\s+", " ", team).strip()
            if len(team) < 3:
                team = None

        return team, ml
