"""
Quick test — run each scraper and print what it finds.
Run: python test_scrapers.py

Install first:
  pip install playwright aiohttp beautifulsoup4 lxml loguru python-dotenv
  playwright install chromium
"""
import asyncio
import sys
import os

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def test_hdlinea():
    print("\n" + "="*50)
    print("  TESTING: HDLinea (no login needed)")
    print("="*50)
    from backend.scrapers.hdlinea_scraper import HDLineaScraper

    scraper = HDLineaScraper()
    odds = await scraper.scrape()

    if odds:
        print(f"\n✅ SUCCESS — {len(odds)} odds found\n")
        for o in odds[:10]:
            print(f"  {o.home_team:25} vs {o.away_team:25} | {o.outcome:4} | {o.odds_value:.3f} | {o.sport_code}")
        if len(odds) > 10:
            print(f"  ... and {len(odds)-10} more")
    else:
        print("\n❌ No odds found — check HDLinea sport IDs")

    return odds


async def test_betcris():
    print("\n" + "="*50)
    print("  TESTING: Betcris (Playwright login)")
    print("="*50)
    print(f"  Username: {os.getenv('BETCRIS_USERNAME')}")

    from backend.scrapers.betcris_scraper import BetcrisScraper

    scraper = BetcrisScraper()
    odds = await scraper.scrape()

    if odds:
        print(f"\n✅ SUCCESS — {len(odds)} odds found\n")
        for o in odds[:10]:
            print(f"  {o.home_team:25} vs {o.away_team:25} | {o.outcome:4} | {o.odds_value:.3f} | {o.sport_code}")
    else:
        print("\n❌ No odds found — login may have failed or page structure changed")

    return odds


async def test_juancito():
    print("\n" + "="*50)
    print("  TESTING: JuancitoSport (Playwright login)")
    print("="*50)
    print(f"  Username: {os.getenv('JUANCITO_USERNAME')}")

    from backend.scrapers.juancito_scraper import JuancitoScraper

    scraper = JuancitoScraper()
    odds = await scraper.scrape()

    if odds:
        print(f"\n✅ SUCCESS — {len(odds)} odds found\n")
        for o in odds[:10]:
            print(f"  {o.home_team:25} vs {o.away_team:25} | {o.outcome:4} | {o.odds_value:.3f} | {o.sport_code}")
    else:
        print("\n❌ No odds found — login may have failed or page structure changed")

    return odds


async def test_surebet_detection(all_odds):
    print("\n" + "="*50)
    print("  SUREBET DETECTION")
    print("="*50)

    if len(all_odds) < 2:
        print("  Not enough odds to detect surebets")
        return

    from backend.algorithms.surebet_detector import SurebetDetector
    detector = SurebetDetector()
    results = detector.detect(all_odds)

    surebets    = [r for r in results if r.is_profitable]
    near_bets   = [r for r in results if not r.is_profitable]

    print(f"\n  Total odds collected : {len(all_odds)}")
    print(f"  Surebets found       : {len(surebets)}")
    print(f"  Near-surebets found  : {len(near_bets)}")

    if surebets:
        print(f"\n  🎯 SUREBETS:")
        for s in surebets:
            print(f"\n    {s.home_team} vs {s.away_team} ({s.sport_code})")
            print(f"    Margin: +{s.profit_margin:.4f}%  |  IP: {s.total_implied_prob:.4f}")
            for leg in s.legs:
                print(f"      → {leg.bookmaker:15} | {leg.outcome:4} @ {leg.odds:.3f} | stake: {leg.stake_percent:.1f}%")

    if near_bets:
        print(f"\n  ⚡ NEAR SUREBETS (top 3):")
        for s in near_bets[:3]:
            print(f"    {s.home_team} vs {s.away_team} | margin: {s.profit_margin:.4f}% | IP: {s.total_implied_prob:.4f}")


async def main():
    print("\n🎯 Surebet System — Scraper Test")
    print("   Testing all 3 Dominican bookmakers\n")

    all_odds = []

    # Test HDLinea first (no login, fastest)
    try:
        hdlinea_odds = await test_hdlinea()
        all_odds.extend(hdlinea_odds)
    except Exception as e:
        print(f"HDLinea error: {e}")

    # Test Betcris
    try:
        betcris_odds = await test_betcris()
        all_odds.extend(betcris_odds)
    except Exception as e:
        print(f"Betcris error: {e}")

    # Test JuancitoSport
    try:
        juancito_odds = await test_juancito()
        all_odds.extend(juancito_odds)
    except Exception as e:
        print(f"JuancitoSport error: {e}")

    # Run surebet detection on combined data
    await test_surebet_detection(all_odds)

    print("\n" + "="*50)
    print("  Test complete")
    print("="*50 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
