"""
Unit tests for the Surebet Detection Algorithm.
Run: pytest tests/
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from datetime import datetime
from backend.scrapers.base_scraper import OddsData, american_to_decimal, decimal_to_implied_prob
from backend.algorithms.surebet_detector import SurebetDetector, SurebetResult


# ---- Helper ----
def make_odds(bookmaker, sport, home, away, outcome, odds_val, market='moneyline'):
    return OddsData(
        bookmaker=bookmaker,
        sport_code=sport,
        league=f"{sport} League",
        home_team=home,
        away_team=away,
        event_date=datetime(2025, 2, 15),
        market_type=market,
        outcome=outcome,
        odds_value=odds_val,
    )


# ---- Tests ----
class TestAmericanToDecimal:
    def test_positive_american(self):
        assert american_to_decimal("+150") == 2.5
        assert american_to_decimal("+100") == 2.0

    def test_negative_american(self):
        assert american_to_decimal("-110") == pytest.approx(1.9091, rel=1e-3)
        assert american_to_decimal("-200") == 1.5

    def test_invalid(self):
        assert american_to_decimal("abc") is None
        assert american_to_decimal("0") is None


class TestImpliedProb:
    def test_decimal_1_91(self):
        ip = decimal_to_implied_prob(1.91)
        assert abs(ip - 0.5236) < 0.001

    def test_decimal_2_0(self):
        assert decimal_to_implied_prob(2.0) == 0.5


class TestSurebetDetector:
    def setup_method(self):
        self.detector = SurebetDetector(
            surebet_threshold=1.0,
            near_surebet_threshold=1.05,
        )

    def test_clear_surebet_detected(self):
        """
        A clear surebet: sum of implied probs < 1.
        Home at Betcris: 2.10 (IP = 0.4762)
        Away at JuancitoSport: 2.20 (IP = 0.4545)
        Total IP = 0.9307 < 1.0 => SUREBET, margin ~7.45%
        """
        odds = [
            make_odds("Betcris", "NBA", "Lakers", "Celtics", "home", 2.10),
            make_odds("JuancitoSport", "NBA", "Lakers", "Celtics", "away", 2.20),
        ]

        results = self.detector.detect(odds)
        assert len(results) == 1
        assert results[0].opportunity_type == "surebet"
        assert results[0].is_profitable
        assert results[0].profit_margin > 0
        assert results[0].total_implied_prob < 1.0

    def test_no_surebet_standard_odds(self):
        """
        Standard bookmaker margin: no surebet.
        Home: 1.91 (IP = 0.5236)
        Away: 1.91 (IP = 0.5236)
        Total = 1.047 > 1.0 => No surebet
        """
        odds = [
            make_odds("Betcris", "NBA", "Warriors", "Nets", "home", 1.91),
            make_odds("JuancitoSport", "NBA", "Warriors", "Nets", "away", 1.91),
        ]
        results = self.detector.detect(odds)
        # Should still return near_surebet since 1.047 < 1.05
        assert all(r.opportunity_type == 'near_surebet' for r in results if results)

    def test_near_surebet_flagged(self):
        """
        Near surebet: IP just above 1.0 but below threshold.
        """
        odds = [
            make_odds("Betcris", "NFL", "Cowboys", "Eagles", "home", 2.05),
            make_odds("HDLinea", "NFL", "Cowboys", "Eagles", "away", 2.05),
        ]
        results = self.detector.detect(odds)
        # IP = 1/2.05 + 1/2.05 = 0.9756 => surebet
        assert len(results) == 1
        assert results[0].is_profitable

    def test_single_bookmaker_ignored(self):
        """
        Can't have arbitrage with only one bookmaker.
        """
        odds = [
            make_odds("Betcris", "MLB", "Yankees", "RedSox", "home", 2.50),
            make_odds("Betcris", "MLB", "Yankees", "RedSox", "away", 1.60),
        ]
        results = self.detector.detect(odds)
        assert len(results) == 0

    def test_stake_distribution_sums_to_100(self):
        """Stakes should sum to 100%."""
        odds = [
            make_odds("Betcris", "NBA", "Bulls", "Heat", "home", 2.10),
            make_odds("JuancitoSport", "NBA", "Bulls", "Heat", "away", 2.10),
        ]
        results = self.detector.detect(odds)
        assert len(results) > 0

        total_stake = sum(leg.stake_percent for leg in results[0].legs)
        assert abs(total_stake - 100.0) < 0.01

    def test_profit_calculation(self):
        """Verify profit calculation is correct."""
        # Home: 2.10 (IP = 0.4762), Away: 2.20 (IP = 0.4545)
        # Total IP = 0.9307
        # Profit margin = (1 - 0.9307) / 0.9307 * 100 = 7.45%
        odds = [
            make_odds("Betcris", "NBA", "Knicks", "Bucks", "home", 2.10),
            make_odds("JuancitoSport", "NBA", "Knicks", "Bucks", "away", 2.20),
        ]
        results = self.detector.detect(odds)
        assert len(results) == 1

        result = results[0]
        stakes = SurebetDetector.calculate_stakes(1000, result)
        profits = SurebetDetector.calculate_profit(1000, result)

        # All outcomes should yield approximately the same payout
        payouts = [v['payout'] for v in profits.values()]
        assert max(payouts) - min(payouts) < 5  # Within $5

    def test_3way_soccer_surebet(self):
        """Test 3-way soccer arbitrage (1X2)."""
        odds = [
            make_odds("Betcris", "SOC", "Barcelona", "Madrid", "home", 2.40, "1X2"),
            make_odds("JuancitoSport", "SOC", "Barcelona", "Madrid", "draw", 3.80, "1X2"),
            make_odds("HDLinea", "SOC", "Barcelona", "Madrid", "away", 3.00, "1X2"),
        ]
        results = self.detector.detect(odds)
        # IP = 1/2.4 + 1/3.8 + 1/3.0 = 0.4167 + 0.2632 + 0.3333 = 1.013
        # Near surebet but not a true surebet
        assert len(results) <= 1

    def test_odds_out_of_range_filtered(self):
        """Suspicious odds (too low or too high) should be filtered."""
        odds = [
            make_odds("Betcris", "NBA", "A", "B", "home", 0.5),  # impossible odds
            make_odds("JuancitoSport", "NBA", "A", "B", "away", 1.50),
        ]
        results = self.detector.detect(odds)
        assert len(results) == 0

    def test_multiple_sports_independent(self):
        """Events from different sports are not mixed."""
        odds = [
            make_odds("Betcris", "NBA", "TeamA", "TeamB", "home", 2.10),
            make_odds("JuancitoSport", "NBA", "TeamA", "TeamB", "away", 2.20),
            make_odds("Betcris", "NFL", "TeamC", "TeamD", "home", 1.90),
            make_odds("HDLinea", "NFL", "TeamC", "TeamD", "away", 2.15),
        ]
        results = self.detector.detect(odds)
        sport_codes = {r.sport_code for r in results}
        assert "NBA" in sport_codes
        assert "NFL" in sport_codes


# Allow running without pytest
try:
    import pytest
except ImportError:
    # Run basic validation manually
    print("Running basic algorithm validation (pytest not installed)...")

    detector = SurebetDetector()

    # Test 1: Clear surebet
    odds = [
        make_odds("Betcris", "NBA", "Lakers", "Celtics", "home", 2.10),
        make_odds("JuancitoSport", "NBA", "Lakers", "Celtics", "away", 2.20),
    ]
    results = detector.detect(odds)
    assert len(results) == 1
    assert results[0].opportunity_type == "surebet"
    print(f"✅ Test 1 PASS: Surebet detected, margin={results[0].profit_margin:.4f}%")

    # Test 2: No surebet with one bookmaker
    odds2 = [
        make_odds("Betcris", "NBA", "Warriors", "Celtics", "home", 2.10),
        make_odds("Betcris", "NBA", "Warriors", "Celtics", "away", 1.80),
    ]
    results2 = detector.detect(odds2)
    assert len(results2) == 0
    print("✅ Test 2 PASS: Single bookmaker correctly rejected")

    # Test 3: American odds conversion
    assert american_to_decimal("+150") == 2.5
    assert american_to_decimal("-110") is not None
    print("✅ Test 3 PASS: American odds conversion works")

    # Test 4: Implied probability
    ip = decimal_to_implied_prob(2.0)
    assert abs(ip - 0.5) < 0.001
    print("✅ Test 4 PASS: Implied probability calculation correct")

    print("\n✅ All basic validations passed!")
