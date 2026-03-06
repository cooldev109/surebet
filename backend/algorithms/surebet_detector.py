"""
Surebet Detection Algorithm.

A surebet (arbitrage bet) exists when the sum of implied probabilities
across all outcomes from different bookmakers is less than 1.0.

Formula:
  For a 2-way market (moneyline):
    IP = 1/odds_A_home + 1/odds_B_away
    If IP < 1.0 => SUREBET (guaranteed profit)
    If 1.0 <= IP <= 1.05 => NEAR SUREBET (watch closely)

  Profit margin = (1 - IP) / IP * 100%
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from itertools import combinations
from typing import Optional
from loguru import logger


def _token_similarity(name1: str, name2: str) -> float:
    """
    Token-based Jaccard similarity between two normalized team name strings.

    Examples:
        "golden state warriors" vs "golden state"  -> 0.88 (subset boost)
        "los angeles lakers"    vs "lakers"         -> 0.88 (subset boost)
        "new york knicks"       vs "new york giants" -> 0.5  (no match)
    """
    if name1 == name2:
        return 1.0
    if not name1 or not name2:
        return 0.0
    t1 = set(name1.split())
    t2 = set(name2.split())
    if not t1 or not t2:
        return 0.0
    intersection = len(t1 & t2)
    union = len(t1 | t2)
    jaccard = intersection / union
    # If one name is a strict subset of the other (e.g. "lakers" ⊂ "la lakers")
    # give a strong boost — they almost certainly refer to the same team.
    if t1 <= t2 or t2 <= t1:
        return max(jaccard, 0.88)
    return jaccard

from ..scrapers.base_scraper import OddsData, decimal_to_implied_prob


@dataclass
class BetLeg:
    """A single leg of a surebet (one outcome at one bookmaker)."""
    bookmaker: str
    team: str
    outcome: str       # 'home', 'away', 'draw'
    odds: float
    implied_prob: float
    stake_percent: float = 0.0  # Recommended % of bankroll on this leg


@dataclass
class SurebetResult:
    """A detected surebet or near-surebet opportunity."""
    event_key: str
    home_team: str
    away_team: str
    sport_code: str
    league: str
    market_type: str
    opportunity_type: str       # 'surebet' | 'near_surebet'
    total_implied_prob: float   # Sum of IPs (< 1.0 = surebet)
    profit_margin: float        # As percentage (e.g., 2.5 for 2.5%)
    legs: list[BetLeg]
    detected_at: datetime = field(default_factory=datetime.utcnow)
    event_date: Optional[datetime] = None

    @property
    def is_profitable(self) -> bool:
        return self.total_implied_prob < 1.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["detected_at"] = self.detected_at.isoformat()
        if self.event_date:
            d["event_date"] = self.event_date.isoformat()
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class SurebetDetector:
    """
    Detects surebet and near-surebet opportunities across multiple bookmakers.

    Algorithm:
    1. Group odds by normalized event key + market type
    2. For each event/market, collect best odds per outcome per bookmaker
    3. Find the combination of bookmakers that minimizes total implied probability
    4. If sum(IP) < 1.0 => surebet; if < threshold => near-surebet
    """

    def __init__(
        self,
        surebet_threshold: float = 1.0,
        near_surebet_threshold: float = 1.05,
        min_odds: float = 1.05,
        max_odds: float = 50.0,
    ):
        self.surebet_threshold = surebet_threshold
        self.near_surebet_threshold = near_surebet_threshold
        self.min_odds = min_odds
        self.max_odds = max_odds

    def detect(self, odds_list: list[OddsData]) -> list[SurebetResult]:
        """
        Main detection entry point.
        Returns list of surebet/near-surebet opportunities.
        """
        if not odds_list:
            return []

        # Group by event key + market type
        grouped = self._group_odds(odds_list)

        results = []
        for (event_key, market_type), event_odds in grouped.items():
            opportunities = self._analyze_event(event_key, market_type, event_odds)
            results.extend(opportunities)

        # Sort by profitability (best first)
        results.sort(key=lambda x: x.total_implied_prob)

        logger.info(
            f"Detection complete: {len(results)} opportunities found "
            f"({sum(1 for r in results if r.is_profitable)} surebets, "
            f"{sum(1 for r in results if not r.is_profitable)} near-surebets)"
        )

        return results

    def _group_odds(
        self, odds_list: list[OddsData]
    ) -> dict[tuple[str, str], list[OddsData]]:
        """
        Group odds by (normalized_event_key, market_type).

        Two passes:
        1. Exact key grouping (fast path — covers alias-expanded names)
        2. Fuzzy merge of groups with very similar event keys (catches
           residual name differences the alias table didn't resolve)
        """
        grouped: dict[tuple[str, str], list[OddsData]] = {}

        for odds in odds_list:
            if not self.min_odds <= odds.odds_value <= self.max_odds:
                continue  # Filter out suspicious odds

            key = (odds.normalized_key, odds.market_type)
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(odds)

        # Second pass: merge groups whose keys refer to the same real-world event
        grouped = self._fuzzy_merge_groups(grouped)
        return grouped

    def _fuzzy_merge_groups(
        self,
        grouped: dict[tuple[str, str], list[OddsData]],
    ) -> dict[tuple[str, str], list[OddsData]]:
        """
        Merge event groups whose normalized keys are highly similar.

        This handles residual name differences not covered by the alias table,
        e.g. "portland trail blazers" vs "portland" after alias expansion.

        The first key encountered for a similar pair is used as the canonical key
        (arbitrary but consistent within one scraping cycle).
        """
        keys = list(grouped.keys())
        # Maps each key -> its canonical representative key
        canonical: dict[tuple[str, str], tuple[str, str]] = {}

        for i, ki in enumerate(keys):
            if ki in canonical:
                continue
            for j in range(i + 1, len(keys)):
                kj = keys[j]
                if kj in canonical:
                    continue
                # Market types must be identical
                if ki[1] != kj[1]:
                    continue
                if self._event_keys_similar(ki[0], kj[0]):
                    canonical[kj] = ki  # merge kj into ki
                    logger.debug(
                        f"Fuzzy merge: '{kj[0]}' -> '{ki[0]}'"
                    )

        if not canonical:
            return grouped  # Nothing to merge — fast path

        result: dict[tuple[str, str], list[OddsData]] = {}
        for key, odds_list in grouped.items():
            target = canonical.get(key, key)
            if target not in result:
                result[target] = []
            result[target].extend(odds_list)
        return result

    @staticmethod
    def _event_keys_similar(key1: str, key2: str, threshold: float = 0.82) -> bool:
        """
        Return True if two event key strings likely represent the same game.

        Keys have the format: "SPORT_CODE:home_team:away_team"
        Both home AND away names must independently meet the similarity threshold.

        Threshold 0.82 is intentionally conservative to avoid false merges
        (e.g. "new york knicks" vs "new york giants" → 0.5 → no merge).
        """
        parts1 = key1.split(":")
        parts2 = key2.split(":")

        if len(parts1) < 3 or len(parts2) < 3:
            return False

        # Sport codes must match exactly
        if parts1[0] != parts2[0]:
            return False

        home_sim = _token_similarity(parts1[1], parts2[1])
        away_sim = _token_similarity(parts1[2], parts2[2])
        return home_sim >= threshold and away_sim >= threshold

    def _analyze_event(
        self,
        event_key: str,
        market_type: str,
        odds_list: list[OddsData],
    ) -> list[SurebetResult]:
        """
        Analyze a single event/market for surebet opportunities.
        Tries all combinations of bookmakers for each outcome.
        """
        results = []

        # Get unique outcomes and bookmakers
        outcomes = list({o.outcome for o in odds_list})
        bookmakers = list({o.bookmaker for o in odds_list})

        if len(bookmakers) < 2:
            return []  # Need at least 2 bookmakers for arbitrage

        # Get best odds per bookmaker per outcome
        best_by_bm_outcome: dict[tuple[str, str], OddsData] = {}
        for odds in odds_list:
            key = (odds.bookmaker, odds.outcome)
            if key not in best_by_bm_outcome or odds.odds_value > best_by_bm_outcome[key].odds_value:
                best_by_bm_outcome[key] = odds

        # For 2-way markets (moneyline: home/away)
        if "draw" not in outcomes and len(outcomes) == 2:
            result = self._check_2way_arbitrage(
                event_key, market_type, outcomes, best_by_bm_outcome
            )
            if result:
                results.append(result)

        # For 3-way markets (1X2: home/draw/away - soccer)
        elif "draw" in outcomes and len(outcomes) == 3:
            result = self._check_3way_arbitrage(
                event_key, market_type, best_by_bm_outcome
            )
            if result:
                results.append(result)

        return results

    def _check_2way_arbitrage(
        self,
        event_key: str,
        market_type: str,
        outcomes: list[str],
        best_by_bm_outcome: dict[tuple[str, str], OddsData],
    ) -> Optional[SurebetResult]:
        """Check 2-way market (e.g., NBA moneyline) for arbitrage."""
        outcome_a, outcome_b = outcomes[0], outcomes[1]
        bookmakers = list({bm for (bm, _) in best_by_bm_outcome.keys()})

        best_result = None
        best_ip = float("inf")

        # Try all combinations of bookmakers for each outcome
        for bm_a in bookmakers:
            for bm_b in bookmakers:
                odds_a = best_by_bm_outcome.get((bm_a, outcome_a))
                odds_b = best_by_bm_outcome.get((bm_b, outcome_b))

                if not odds_a or not odds_b:
                    continue

                ip_a = decimal_to_implied_prob(odds_a.odds_value)
                ip_b = decimal_to_implied_prob(odds_b.odds_value)
                total_ip = ip_a + ip_b

                if total_ip < best_ip:
                    best_ip = total_ip
                    best_result = (odds_a, odds_b, ip_a, ip_b, total_ip)

        if not best_result:
            return None

        odds_a, odds_b, ip_a, ip_b, total_ip = best_result

        if total_ip > self.near_surebet_threshold:
            return None  # Not interesting enough

        # Calculate optimal stake distribution
        # stake_a = (ip_a / total_ip) * 100%  of bankroll
        stake_a = round(ip_a / total_ip * 100, 2)
        stake_b = round(ip_b / total_ip * 100, 2)
        profit_margin = round((1 - total_ip) / total_ip * 100, 4)

        opportunity_type = "surebet" if total_ip < self.surebet_threshold else "near_surebet"

        legs = [
            BetLeg(
                bookmaker=odds_a.bookmaker,
                team=odds_a.home_team if odds_a.outcome == "home" else odds_a.away_team,
                outcome=odds_a.outcome,
                odds=odds_a.odds_value,
                implied_prob=round(ip_a, 4),
                stake_percent=stake_a,
            ),
            BetLeg(
                bookmaker=odds_b.bookmaker,
                team=odds_b.home_team if odds_b.outcome == "home" else odds_b.away_team,
                outcome=odds_b.outcome,
                odds=odds_b.odds_value,
                implied_prob=round(ip_b, 4),
                stake_percent=stake_b,
            ),
        ]

        return SurebetResult(
            event_key=event_key,
            home_team=odds_a.home_team,
            away_team=odds_a.away_team,
            sport_code=odds_a.sport_code,
            league=odds_a.league,
            market_type=market_type,
            opportunity_type=opportunity_type,
            total_implied_prob=round(total_ip, 6),
            profit_margin=profit_margin,
            legs=legs,
            event_date=odds_a.event_date,
        )

    def _check_3way_arbitrage(
        self,
        event_key: str,
        market_type: str,
        best_by_bm_outcome: dict[tuple[str, str], OddsData],
    ) -> Optional[SurebetResult]:
        """Check 3-way market (soccer 1X2) for arbitrage."""
        bookmakers = list({bm for (bm, _) in best_by_bm_outcome.keys()})

        best_result = None
        best_ip = float("inf")

        for bm_home in bookmakers:
            for bm_draw in bookmakers:
                for bm_away in bookmakers:
                    odds_home = best_by_bm_outcome.get((bm_home, "home"))
                    odds_draw = best_by_bm_outcome.get((bm_draw, "draw"))
                    odds_away = best_by_bm_outcome.get((bm_away, "away"))

                    if not all([odds_home, odds_draw, odds_away]):
                        continue

                    ip_home = decimal_to_implied_prob(odds_home.odds_value)
                    ip_draw = decimal_to_implied_prob(odds_draw.odds_value)
                    ip_away = decimal_to_implied_prob(odds_away.odds_value)
                    total_ip = ip_home + ip_draw + ip_away

                    if total_ip < best_ip:
                        best_ip = total_ip
                        best_result = (odds_home, odds_draw, odds_away, ip_home, ip_draw, ip_away, total_ip)

        if not best_result:
            return None

        odds_home, odds_draw, odds_away, ip_home, ip_draw, ip_away, total_ip = best_result

        if total_ip > self.near_surebet_threshold:
            return None

        stake_home = round(ip_home / total_ip * 100, 2)
        stake_draw = round(ip_draw / total_ip * 100, 2)
        stake_away = round(ip_away / total_ip * 100, 2)
        profit_margin = round((1 - total_ip) / total_ip * 100, 4)
        opportunity_type = "surebet" if total_ip < self.surebet_threshold else "near_surebet"

        legs = [
            BetLeg(
                bookmaker=odds_home.bookmaker,
                team=odds_home.home_team,
                outcome="home",
                odds=odds_home.odds_value,
                implied_prob=round(ip_home, 4),
                stake_percent=stake_home,
            ),
            BetLeg(
                bookmaker=odds_draw.bookmaker,
                team="Draw",
                outcome="draw",
                odds=odds_draw.odds_value,
                implied_prob=round(ip_draw, 4),
                stake_percent=stake_draw,
            ),
            BetLeg(
                bookmaker=odds_away.bookmaker,
                team=odds_away.away_team,
                outcome="away",
                odds=odds_away.odds_value,
                implied_prob=round(ip_away, 4),
                stake_percent=stake_away,
            ),
        ]

        return SurebetResult(
            event_key=event_key,
            home_team=odds_home.home_team,
            away_team=odds_home.away_team,
            sport_code=odds_home.sport_code,
            league=odds_home.league,
            market_type=market_type,
            opportunity_type=opportunity_type,
            total_implied_prob=round(total_ip, 6),
            profit_margin=profit_margin,
            legs=legs,
            event_date=odds_home.event_date,
        )

    @staticmethod
    def calculate_stakes(total_bankroll: float, result: SurebetResult) -> dict[str, float]:
        """
        Calculate exact stake amounts for a given bankroll.

        Returns dict of {bookmaker_outcome: stake_amount}
        """
        stakes = {}
        for leg in result.legs:
            stake = total_bankroll * (leg.stake_percent / 100)
            key = f"{leg.bookmaker} - {leg.team} ({leg.outcome})"
            stakes[key] = round(stake, 2)

        return stakes

    @staticmethod
    def calculate_profit(total_bankroll: float, result: SurebetResult) -> dict:
        """
        Calculate expected profit and returns for each outcome.
        """
        stakes = SurebetDetector.calculate_stakes(total_bankroll, result)
        profits = {}

        for i, leg in enumerate(result.legs):
            stake = total_bankroll * (leg.stake_percent / 100)
            payout = stake * leg.odds
            profit = payout - total_bankroll
            key = f"{leg.bookmaker} - {leg.team}"
            profits[key] = {
                "stake": round(stake, 2),
                "payout": round(payout, 2),
                "profit": round(profit, 2),
                "roi_percent": round((profit / total_bankroll) * 100, 4),
            }

        return profits
