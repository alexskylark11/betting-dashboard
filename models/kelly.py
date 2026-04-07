"""Kelly criterion bankroll sizing for sports betting."""

from utils.odds_math import american_to_decimal


def kelly_fraction(model_prob: float, american_odds: int) -> float:
    """Full Kelly fraction of bankroll to wager.

    f* = (b*p - q) / b
    where b = decimal_odds - 1, p = model_prob, q = 1 - p
    """
    b = american_to_decimal(american_odds) - 1
    p = model_prob
    q = 1 - p
    if b <= 0:
        return 0.0
    f = (b * p - q) / b
    return max(f, 0.0)


def kelly_bet_size(
    bankroll: float,
    model_prob: float,
    american_odds: int,
    fraction: float = 0.25,
    max_pct: float = 0.05,
) -> float:
    """Dollar amount to wager using fractional Kelly.

    Args:
        bankroll: current bankroll balance
        model_prob: model's estimated win probability
        american_odds: best available American odds
        fraction: Kelly fraction multiplier (0.25 = quarter-Kelly)
        max_pct: max % of bankroll per bet (safety cap)

    Returns:
        Dollar amount to wager (0 if no edge).
    """
    f = kelly_fraction(model_prob, american_odds)
    if f <= 0:
        return 0.0
    bet_pct = min(f * fraction, max_pct)
    return round(bankroll * bet_pct, 2)
