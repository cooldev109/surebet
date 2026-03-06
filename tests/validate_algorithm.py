"""
Standalone validation of the surebet algorithm (no external dependencies).
Run: python tests/validate_algorithm.py
"""

def american_to_decimal(american: str):
    try:
        val = int(american.replace("+", "").strip())
        if val == 0:
            return None
        if val > 0:
            return round(1 + val / 100, 4)
        else:
            return round(1 + 100 / abs(val), 4)
    except (ValueError, ZeroDivisionError):
        return None


def decimal_to_implied_prob(decimal_odds: float) -> float:
    if decimal_odds <= 0:
        return 0.0
    return round(1 / decimal_odds, 6)


def detect_surebet_2way(odds_home: float, odds_away: float):
    ip_home = decimal_to_implied_prob(odds_home)
    ip_away = decimal_to_implied_prob(odds_away)
    total_ip = ip_home + ip_away

    profit_margin = (1 - total_ip) / total_ip * 100

    return {
        "total_ip": round(total_ip, 6),
        "profit_margin": round(profit_margin, 4),
        "is_surebet": total_ip < 1.0,
        "stake_home_pct": round(ip_home / total_ip * 100, 2),
        "stake_away_pct": round(ip_away / total_ip * 100, 2),
    }


def calculate_stakes(bankroll: float, stake_home_pct: float, stake_away_pct: float,
                     odds_home: float, odds_away: float):
    stake_home = bankroll * stake_home_pct / 100
    stake_away = bankroll * stake_away_pct / 100

    payout_home = stake_home * odds_home
    payout_away = stake_away * odds_away

    return {
        "stake_home": round(stake_home, 2),
        "stake_away": round(stake_away, 2),
        "payout_if_home_wins": round(payout_home, 2),
        "payout_if_away_wins": round(payout_away, 2),
        "min_profit": round(min(payout_home, payout_away) - bankroll, 2),
    }


def run_tests():
    print("=" * 55)
    print("  SUREBET ALGORITHM VALIDATION")
    print("=" * 55)
    passed = 0
    failed = 0

    def check(name, condition, detail=""):
        nonlocal passed, failed
        if condition:
            print(f"  PASS  {name}")
            if detail:
                print(f"         {detail}")
            passed += 1
        else:
            print(f"  FAIL  {name}")
            if detail:
                print(f"         {detail}")
            failed += 1

    print("\n[1] American Odds Conversion")
    check("+150 -> 2.5", american_to_decimal("+150") == 2.5)
    check("+100 -> 2.0", american_to_decimal("+100") == 2.0)
    r = american_to_decimal("-110")
    check("-110 -> ~1.909", r is not None and abs(r - 1.9091) < 0.001, f"got {r}")
    check("-200 -> 1.5", american_to_decimal("-200") == 1.5)
    check("invalid -> None", american_to_decimal("abc") is None)

    print("\n[2] Implied Probability")
    check("2.0 -> 50%", decimal_to_implied_prob(2.0) == 0.5)
    ip = decimal_to_implied_prob(1.91)
    check("1.91 -> ~52.36%", abs(ip - 0.5236) < 0.001, f"got {ip:.4f}")

    print("\n[3] Clear Surebet Detection (NBA Example)")
    # Lakers at Betcris: 2.10, Celtics at JuancitoSport: 2.20
    result = detect_surebet_2way(2.10, 2.20)
    print(f"         Lakers(2.10) vs Celtics(2.20)")
    print(f"         Total IP: {result['total_ip']:.4f}")
    print(f"         Profit margin: {result['profit_margin']:.4f}%")
    check("Is surebet", result['is_surebet'])
    check("Profit > 0", result['profit_margin'] > 0)
    check("IP < 1.0", result['total_ip'] < 1.0)

    stakes = calculate_stakes(1000, result['stake_home_pct'], result['stake_away_pct'], 2.10, 2.20)
    check("Stakes sum to ~$1000", abs(stakes['stake_home'] + stakes['stake_away'] - 1000) < 1)
    check("Profit on any outcome > 0", stakes['min_profit'] > 0, f"min profit: ${stakes['min_profit']}")
    print(f"         Stakes: ${stakes['stake_home']} on Home, ${stakes['stake_away']} on Away")
    print(f"         Payout (home wins): ${stakes['payout_if_home_wins']}")
    print(f"         Payout (away wins): ${stakes['payout_if_away_wins']}")

    print("\n[4] No Surebet (Standard Margin)")
    # Both at 1.91 - typical juice
    result2 = detect_surebet_2way(1.91, 1.91)
    print(f"         Both teams at 1.91 (typical -110 American)")
    print(f"         Total IP: {result2['total_ip']:.4f}")
    print(f"         Margin: {result2['profit_margin']:.4f}%")
    check("Not a surebet", not result2['is_surebet'])
    check("Bookmaker margin ~4.7%", abs(abs(result2['profit_margin']) - 4.71) < 0.1,
          f"got {result2['profit_margin']:.4f}%")

    print("\n[5] Near Surebet (Margin < 5% above breakeven)")
    result3 = detect_surebet_2way(2.04, 2.04)
    print(f"         Both teams at 2.04")
    print(f"         Total IP: {result3['total_ip']:.4f}")
    is_near = 1.0 <= result3['total_ip'] <= 1.05
    check("Near surebet range (1.0-1.05)", is_near, f"IP={result3['total_ip']:.4f}")

    print("\n[6] Real-world NFL Example")
    # Cowboys -110 at Betcris, Eagles +105 at JuancitoSport
    cowboys = american_to_decimal("-110")
    eagles = american_to_decimal("+105")
    result4 = detect_surebet_2way(cowboys, eagles)
    print(f"         Cowboys -110 ({cowboys}) vs Eagles +105 ({eagles})")
    print(f"         Total IP: {result4['total_ip']:.4f}")
    print(f"         Margin: {result4['profit_margin']:.4f}%")
    check("IP calculated", result4['total_ip'] > 0)

    print("\n[7] Optimal Stake for $10,000 bankroll")
    result_main = detect_surebet_2way(2.10, 2.20)
    stakes_10k = calculate_stakes(
        10000,
        result_main['stake_home_pct'],
        result_main['stake_away_pct'],
        2.10, 2.20
    )
    print(f"         Bankroll: $10,000")
    print(f"         Bet Home ${stakes_10k['stake_home']} @ 2.10 -> Payout ${stakes_10k['payout_if_home_wins']}")
    print(f"         Bet Away ${stakes_10k['stake_away']} @ 2.20 -> Payout ${stakes_10k['payout_if_away_wins']}")
    print(f"         Guaranteed profit: ${stakes_10k['min_profit']}")
    check("Guaranteed profit > $0", stakes_10k['min_profit'] > 0)
    payout_diff = abs(stakes_10k['payout_if_home_wins'] - stakes_10k['payout_if_away_wins'])
    check("Both outcomes ~equal payout", payout_diff < 50, f"Diff: ${payout_diff:.2f}")

    print("\n" + "=" * 55)
    print(f"  Results: {passed} PASSED, {failed} FAILED")
    print("=" * 55)
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)
