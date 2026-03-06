"""
HDLinea (hdlinea.com.do) scraper.
No login needed. ASP pages with HTML tables.
Uses simple HTTP requests — no Playwright required.
SSL verification disabled (their cert is invalid).

NOTE: This site is geo-restricted to Dominican Republic IPs.
      It will return empty game rows when accessed from outside DR.
      Run the application on a machine located in Dominican Republic.

Sport IDs confirmed from the site's dropdown:
  12=MLB, 13=NBA, 14=NHL, 17=C-BK (NCAAB), 23=SOC, 56=EU-BK
"""
import os
import re
import asyncio
from datetime import datetime
from typing import Optional
from bs4 import BeautifulSoup
from loguru import logger

from .base_scraper import BaseScraper, OddsData, american_to_decimal


BASE_URL = os.getenv("HDLINEA_URL", "http://hdlinea.com.do")

# Sport IDs confirmed directly from HDLinea's sport dropdown
HDLINEA_SPORTS = [
    ("NBA",   13, "NBA"),
    ("MLB",   12, "MLB"),
    ("NHL",   14, "NHL"),
    ("NCAAB", 17, "NCAA Basketball"),   # C-BK = College Basketball
    ("SOC",   23, "Soccer"),
    ("EUROL", 56, "EuroLiga"),          # EU-BK
]


class HDLineaScraper(BaseScraper):
    """Simple HTTP scraper for HDLinea — no JS, no login needed.

    Requires a Dominican Republic IP to receive game data.
    Must visit homepage first to obtain the ASP session cookie.
    """

    _REQUEST_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-DO,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Referer": "http://hdlinea.com.do/",
        "Connection": "keep-alive",
    }

    def __init__(self):
        super().__init__("HDLinea", BASE_URL)

    async def scrape(self) -> list[OddsData]:
        import aiohttp

        all_odds: list[OddsData] = []
        connector = aiohttp.TCPConnector(ssl=False)
        proxy_url = os.getenv("PROXY_URL", "").strip() or None

        async with aiohttp.ClientSession(
            connector=connector,
            headers=self._REQUEST_HEADERS,
        ) as session:
            # Visit homepage first to get ASPSESSIONID cookie
            try:
                async with session.get(
                    f"{BASE_URL}/",
                    timeout=aiohttp.ClientTimeout(total=15),
                    proxy=proxy_url,
                ) as resp:
                    await resp.read()
                    self.logger.debug(
                        f"HDLinea homepage: {resp.status}, "
                        f"cookies={list(session.cookie_jar)}"
                    )
            except Exception as e:
                self.logger.warning(f"HDLinea homepage fetch failed: {e}")

            # Scrape each sport sequentially (share the session/cookies)
            for sport_code, sport_id, league in HDLINEA_SPORTS:
                try:
                    odds = await self._scrape_sport(session, sport_code, sport_id, league, proxy_url)
                    all_odds.extend(odds)
                    if odds:
                        self.logger.info(f"HDLinea {sport_code}: {len(odds)} odds")
                    else:
                        self.logger.debug(f"HDLinea {sport_code}: 0 odds (empty or geo-blocked)")
                except Exception as e:
                    self.logger.error(f"HDLinea {sport_code}: {e}")

        return all_odds

    async def _scrape_sport(
        self, session, sport_code: str, sport_id: int, league: str, proxy: str = None
    ) -> list[OddsData]:
        """Fetch odds for a single sport using the confirmed sport ID."""
        import aiohttp

        url = (
            f"{BASE_URL}/lineas.asp"
            f"?Id_opcion=&Id_tipoall=&fechatox=0&Iddeporte={sport_id}"
        )

        for attempt in range(3):
            try:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=20), proxy=proxy
                ) as resp:
                    if resp.status != 200:
                        self.logger.warning(f"HDLinea {sport_code} HTTP {resp.status}")
                        return []
                    html = await resp.text(encoding="latin-1", errors="replace")
                    return self._parse_html(html, sport_code, league)
            except Exception as e:
                self.logger.warning(f"HDLinea {sport_code} attempt {attempt+1}/3: {e}")
                if attempt < 2:
                    await asyncio.sleep(1)

        return []

    # ------------------------------------------------------------------ #
    #  HTML Parsing                                                        #
    # ------------------------------------------------------------------ #
    def _parse_html(self, html: str, sport_code: str, league: str) -> list[OddsData]:
        soup = BeautifulSoup(html, "lxml")
        raw_entries = []

        for table in soup.find_all("table"):
            raw_entries.extend(self._parse_table(table, sport_code, league))

        return self._pair_teams(raw_entries)

    def _parse_table(self, table, sport_code: str, league: str) -> list[OddsData]:
        """
        Parse one HTML table.

        HDLinea 10-column format (confirmed from live HTML inspection):
          [0] Time fragment  "8:00" (away row) | "PM" (home row)
          [1] Rotation       "65" (2-digit)
          [2] Team name      "UTAH", "MEMPHIS"
          [3] Spread+Juice   "+1-110" (combined string, ignored)
          [4] O/U total      "238½" (away row) | O/U juice "-110" (home row)
          [5-6] empty
          [7] Moneyline      "-135", "+105" — ONLY shown on some games
          [8-9] empty

        Games are listed in consecutive pairs (away row first, home row second).
        Only games with explicit ML in column [7] are processed.
        """
        entries = []
        current_date: Optional[datetime] = None

        for row in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
            if not cells:
                continue

            row_text = " ".join(cells)

            # Detect date header rows
            date = self._try_parse_date(row_text)
            if date and len(cells) <= 4:
                current_date = date
                continue

            # Skip column header rows
            if any(kw in row_text.lower() for kw in
                   ["fecha", "equipo", "team", "date", "rot#", "visita", "local",
                    "hora", "total", "juego"]):
                continue

            entry = self._parse_line_row(cells, sport_code, league, current_date)
            if entry:
                entries.append(entry)

        return entries

    def _parse_line_row(
        self, cells: list, sport_code: str, league: str, event_date: Optional[datetime]
    ) -> Optional[OddsData]:
        """
        Column-based extraction for HDLinea's 10-column game rows.

        Team is always at index 2.
        Moneyline is at index 7 (only shown for some games).
        Rows without explicit ML are skipped — not useful for surebet detection.
        """
        # Need at least 3 columns for a valid game row
        if len(cells) < 3:
            return None

        # --- Team name (column 2) ---
        team_name = cells[2].strip() if len(cells) > 2 else ""
        if not team_name or len(team_name) < 2:
            return None
        if not re.search(r"[a-zA-Z]", team_name):
            return None
        # Skip header/label cells
        if team_name.lower() in {"equipo", "team", "hora", "cod", "local",
                                  "visita", "ml", "rl", "total", "1ra", "ult"}:
            return None

        # --- Moneyline (column 7 — explicit ML column) ---
        ml_raw: Optional[str] = None
        ml_odds: Optional[float] = None

        if len(cells) > 7:
            c7 = cells[7].strip()
            if re.match(r"^[+-]\d{2,4}$", c7):
                ml_raw = c7
                ml_odds = american_to_decimal(c7)

        # Fall back: column 4 is valid odds only for home-team rows
        # (home rows have O/U juice "-110" in col 4; away rows have "238½" total)
        if not ml_odds and len(cells) > 4:
            c4 = cells[4].strip()
            if re.match(r"^[+-]\d{2,4}$", c4):
                # Only use if the value is clearly a proper ML (not ±110 juice)
                # -110 as the sole odds means no explicit ML was posted
                val = american_to_decimal(c4)
                if val and c4 not in ("-110", "-105", "+100"):
                    ml_raw = c4
                    ml_odds = val

        if not team_name or not ml_odds:
            return None

        return OddsData(
            bookmaker="HDLinea",
            sport_code=sport_code,
            league=league,
            home_team=team_name,  # corrected in _pair_teams
            away_team="TBD",
            event_date=event_date,
            market_type="moneyline",
            outcome="home",       # corrected in _pair_teams
            odds_value=ml_odds,
            raw_odds=ml_raw,
        )

    def _pair_teams(self, entries: list[OddsData]) -> list[OddsData]:
        """
        HDLinea lists teams in consecutive pairs:
          Row 1 = Away team (visitante)
          Row 2 = Home team (local)
        """
        paired: list[OddsData] = []
        i = 0
        while i < len(entries) - 1:
            away_entry = entries[i]
            home_entry = entries[i + 1]

            home  = home_entry.home_team
            away  = away_entry.home_team
            edate = home_entry.event_date or away_entry.event_date

            paired.append(OddsData(
                bookmaker="HDLinea",
                sport_code=home_entry.sport_code, league=home_entry.league,
                home_team=home, away_team=away,   event_date=edate,
                market_type="moneyline", outcome="home",
                odds_value=home_entry.odds_value, raw_odds=home_entry.raw_odds,
            ))
            paired.append(OddsData(
                bookmaker="HDLinea",
                sport_code=away_entry.sport_code, league=away_entry.league,
                home_team=home, away_team=away,   event_date=edate,
                market_type="moneyline", outcome="away",
                odds_value=away_entry.odds_value, raw_odds=away_entry.raw_odds,
            ))
            i += 2

        return paired

    def _try_parse_date(self, text: str) -> Optional[datetime]:
        for pattern in [
            r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})",   # 02/19/2026
            r"(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})",   # 2026-02-19
        ]:
            m = re.search(pattern, text)
            if m:
                try:
                    a, b, c = (int(x) for x in m.groups())
                    if c > 31:    return datetime(c, a, b)   # year last
                    elif a > 31:  return datetime(a, b, c)   # year first
                    else:         return datetime(datetime.now().year, a, b)
                except ValueError:
                    pass
        return None
