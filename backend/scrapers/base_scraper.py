"""
Base scraper class for all bookmaker scrapers.
"""
import re
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from loguru import logger


@dataclass
class OddsData:
    """Normalized odds data from any bookmaker."""
    bookmaker: str
    sport_code: str
    league: str
    home_team: str
    away_team: str
    event_date: Optional[datetime]
    market_type: str        # '1X2', 'moneyline', 'spread', 'total'
    outcome: str            # 'home', 'away', 'draw', 'over', 'under'
    odds_value: float       # Decimal odds (e.g., 1.91)
    handicap: Optional[float] = None
    raw_odds: Optional[str] = None
    normalized_key: str = field(default="")

    def __post_init__(self):
        if not self.normalized_key:
            self.normalized_key = self._build_key()

    def _build_key(self) -> str:
        """Build a normalized key to match events across bookmakers.

        Date is intentionally excluded: bookmakers differ in whether they
        expose event dates (HDLinea omits them; Betcris includes them).
        Since we only scrape current/today's lines, the date is implicit
        and excluding it is the only way to match the same game across
        different bookmakers.

        Alias expansion is applied so that abbreviated names used by one
        bookmaker (e.g. HDLinea's "GOLDEN ST") resolve to the same canonical
        form as full names used by another (e.g. Betcris's "Golden State Warriors").
        """
        from .team_aliases import expand_team_alias
        home = expand_team_alias(_normalize_team_name(self.home_team), self.sport_code)
        away = expand_team_alias(_normalize_team_name(self.away_team), self.sport_code)
        return f"{self.sport_code}:{home}:{away}"


def _normalize_team_name(name: str) -> str:
    """Normalize team names for cross-bookmaker matching."""
    name = name.lower().strip()
    # Remove common suffixes
    for suffix in [" fc", " cf", " sc", " ac", " bc", " bk"]:
        name = name.replace(suffix, "")
    # Remove special characters, keep only alphanumeric and spaces
    name = re.sub(r"[^\w\s]", "", name)
    # Collapse multiple spaces
    name = re.sub(r"\s+", " ", name).strip()
    return name


def american_to_decimal(american: str) -> Optional[float]:
    """Convert American odds (+150, -110) to decimal odds."""
    try:
        val = int(american.replace("+", "").strip())
        if val > 0:
            return round(1 + val / 100, 4)
        else:
            return round(1 + 100 / abs(val), 4)
    except (ValueError, ZeroDivisionError):
        return None


def decimal_to_implied_prob(decimal_odds: float) -> float:
    """Convert decimal odds to implied probability."""
    if decimal_odds <= 0:
        return 0.0
    return round(1 / decimal_odds, 6)


class BaseScraper(ABC):
    """Abstract base class for all bookmaker scrapers."""

    def __init__(self, name: str, base_url: str):
        self.name = name
        self.base_url = base_url
        self.logger = logger.bind(scraper=name)
        self._session = None

    @abstractmethod
    async def scrape(self) -> list[OddsData]:
        """
        Scrape and return normalized odds data.
        Must be implemented by each bookmaker scraper.
        """
        pass

    async def _fetch(self, url: str, headers: dict = None, timeout: int = 30) -> Optional[str]:
        """HTTP GET with retry logic."""
        import aiohttp
        from tenacity import retry, stop_after_attempt, wait_exponential

        default_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "es-DO,es;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        if headers:
            default_headers.update(headers)

        for attempt in range(3):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url,
                        headers=default_headers,
                        timeout=aiohttp.ClientTimeout(total=timeout),
                        ssl=False,
                    ) as resp:
                        if resp.status == 200:
                            return await resp.text(errors="replace")
                        else:
                            self.logger.warning(f"HTTP {resp.status} for {url}")
            except Exception as e:
                self.logger.warning(f"Attempt {attempt + 1}/3 failed for {url}: {e}")
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)

        return None

    async def _fetch_json(self, url: str, headers: dict = None) -> Optional[dict]:
        """HTTP GET expecting JSON response."""
        import aiohttp
        import json

        default_headers = {
            "User-Agent": "Mozilla/5.0 (compatible; SurebetBot/1.0)",
            "Accept": "application/json",
        }
        if headers:
            default_headers.update(headers)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=default_headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                    ssl=False,
                ) as resp:
                    if resp.status == 200:
                        return await resp.json(content_type=None)
        except Exception as e:
            self.logger.error(f"JSON fetch failed for {url}: {e}")

        return None
