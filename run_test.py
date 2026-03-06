import asyncio
import sys
import traceback
sys.path.insert(0, '.')

from dotenv import load_dotenv
load_dotenv()

async def test_hdlinea():
    print("--- HDLinea ---")
    try:
        from backend.scrapers.hdlinea_scraper import HDLineaScraper
        s = HDLineaScraper()
        odds = await s.scrape()
        print(f"Found: {len(odds)} odds")
        for o in odds[:10]:
            print(f"  {o.home_team[:20]:20} vs {o.away_team[:20]:20} | {o.outcome:4} | {o.odds_value:.3f} | {o.sport_code}")
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()

async def test_betcris():
    print("\n--- Betcris ---")
    try:
        from backend.scrapers.betcris_scraper import BetcrisScraper
        s = BetcrisScraper()
        odds = await s.scrape()
        print(f"Found: {len(odds)} odds")
        for o in odds[:10]:
            print(f"  {o.home_team[:20]:20} vs {o.away_team[:20]:20} | {o.outcome:4} | {o.odds_value:.3f} | {o.sport_code}")
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()

async def test_juancito():
    print("\n--- JuancitoSport ---")
    try:
        from backend.scrapers.juancito_scraper import JuancitoScraper
        s = JuancitoScraper()
        odds = await s.scrape()
        print(f"Found: {len(odds)} odds")
        for o in odds[:10]:
            print(f"  {o.home_team[:20]:20} vs {o.away_team[:20]:20} | {o.outcome:4} | {o.odds_value:.3f} | {o.sport_code}")
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()

async def main():
    await test_hdlinea()
    await test_betcris()
    await test_juancito()
    print("\nDone.")

asyncio.run(main())
