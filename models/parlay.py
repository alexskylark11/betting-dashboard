"""Parlay optimizer with correlation-aware EV calculation."""

from itertools import combinations
from dataclasses import dataclass
from typing import List
from models.ev_calculator import EVOpportunity
from utils.odds_math import parlay_decimal_odds


@dataclass
class ParlayCandidate:
    legs: List[EVOpportunity]
    combined_decimal_odds: float
    combined_model_prob: float
    ev_per_dollar: float
    leg_count: int


def _joint_probability(legs: List[EVOpportunity], correlation_penalty: float = 0.95) -> float:
    """Estimate joint probability for parlay legs.

    Same-event picks (e.g., two top-10 golfers in the same tournament)
    are slightly negatively correlated — finite spots.
    Cross-sport legs are independent.
    """
    prob = 1.0
    events_seen = set()
    for leg in legs:
        p = leg.model_prob
        # Apply correlation penalty for same-event legs
        if leg.market in events_seen:
            p *= correlation_penalty
        events_seen.add(leg.market)
        prob *= p
    return prob


def find_optimal_parlays(
    ev_bets: List[EVOpportunity],
    max_legs: int = 4,
    min_legs: int = 2,
    min_parlay_ev: float = 0.0,
    max_results: int = 20,
) -> List[ParlayCandidate]:
    """Search all 2-to-N leg combinations from +EV singles pool.

    Args:
        ev_bets: list of +EV single bets
        max_legs: maximum legs per parlay
        min_legs: minimum legs per parlay
        min_parlay_ev: minimum parlay EV to include
        max_results: cap on returned candidates

    Returns:
        List of ParlayCandidate sorted by EV descending.
    """
    candidates = []

    for n in range(min_legs, max_legs + 1):
        for combo in combinations(ev_bets, n):
            legs = list(combo)
            combined_decimal = parlay_decimal_odds([l.decimal_odds for l in legs])
            joint_prob = _joint_probability(legs)
            ev = (joint_prob * (combined_decimal - 1)) - ((1 - joint_prob) * 1.0)

            if ev >= min_parlay_ev:
                candidates.append(ParlayCandidate(
                    legs=legs,
                    combined_decimal_odds=combined_decimal,
                    combined_model_prob=joint_prob,
                    ev_per_dollar=ev,
                    leg_count=n,
                ))

    candidates.sort(key=lambda x: x.ev_per_dollar, reverse=True)
    return candidates[:max_results]
