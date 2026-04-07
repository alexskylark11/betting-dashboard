"""Odds conversion, vig removal, and probability math — pure functions, no I/O."""

from typing import List, Dict


def american_to_decimal(american: int) -> float:
    if american > 0:
        return 1 + american / 100
    return 1 + 100 / abs(american)


def decimal_to_american(decimal_odds: float) -> int:
    if decimal_odds >= 2.0:
        return round((decimal_odds - 1) * 100)
    return round(-100 / (decimal_odds - 1))


def american_to_implied_prob(american: int) -> float:
    if american > 0:
        return 100 / (american + 100)
    return abs(american) / (abs(american) + 100)


def implied_prob_to_american(prob: float) -> int:
    if prob <= 0 or prob >= 1:
        raise ValueError(f"Probability must be between 0 and 1, got {prob}")
    if prob >= 0.5:
        return round(-100 * prob / (1 - prob))
    return round(100 * (1 - prob) / prob)


def calculate_overround(odds_list: List[int]) -> float:
    """Sum of implied probabilities — 1.0 = fair, >1.0 = sportsbook edge."""
    return sum(american_to_implied_prob(o) for o in odds_list)


def remove_vig(odds_dict: Dict[str, int]) -> Dict[str, float]:
    """Normalize implied probs to sum to 1.0 (remove vig/overround).

    Args:
        odds_dict: {player_name: american_odds}

    Returns:
        {player_name: fair_probability}
    """
    raw_probs = {name: american_to_implied_prob(odds) for name, odds in odds_dict.items()}
    total = sum(raw_probs.values())
    if total == 0:
        return raw_probs
    return {name: prob / total for name, prob in raw_probs.items()}


def parlay_decimal_odds(decimal_odds_list: List[float]) -> float:
    """Multiply decimal odds for a parlay."""
    result = 1.0
    for odds in decimal_odds_list:
        result *= odds
    return result


def parlay_american_odds(american_list: List[int]) -> int:
    """Combine American odds for a parlay, return American odds."""
    combined_decimal = parlay_decimal_odds(
        [american_to_decimal(a) for a in american_list]
    )
    return decimal_to_american(combined_decimal)


def ev_from_american(model_prob: float, american_odds: int) -> float:
    """Expected value per $1 wagered.

    Positive = +EV (profitable long-term), negative = -EV.
    """
    decimal_odds = american_to_decimal(american_odds)
    net_profit = decimal_odds - 1  # profit per $1 if win
    return (model_prob * net_profit) - ((1 - model_prob) * 1.0)
