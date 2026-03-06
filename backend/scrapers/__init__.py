"""Scrapers package."""
from .base_scraper import BaseScraper, OddsData, american_to_decimal, decimal_to_implied_prob
from .betcris_scraper import BetcrisScraper
from .juancito_scraper import JuancitoScraper
from .hdlinea_scraper import HDLineaScraper

SCRAPER_REGISTRY = {
    "BetcrisScraper": BetcrisScraper,
    "JuancitoScraper": JuancitoScraper,
    "HDLineaScraper": HDLineaScraper,
}

__all__ = [
    "BaseScraper", "OddsData", "american_to_decimal", "decimal_to_implied_prob",
    "BetcrisScraper", "JuancitoScraper", "HDLineaScraper",
    "SCRAPER_REGISTRY",
]
