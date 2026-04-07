"""Expected value engine — compares model probabilities against sportsbook odds."""

from dataclasses import dataclass
from typing import List, Dict
from utils.odds_math import american_to_implied_prob, ev_from_american, american_to_decimal


@dataclass
class EVOpportunity:
    player: str
    market: str               # outright, top5, top10, top20, h2h
    model_prob: float
    best_book: str
    best_odds: int
    implied_prob: float       # from best available odds (before vig removal)
    edge: float               # model_prob - implied_prob
    ev_per_dollar: float      # expected value per $1 wagered
    decimal_odds: float


def find_ev_bets(
    predictions: Dict[str, float],
    odds_by_book: Dict[str, Dict[str, int]],
    market: str = "outright",
    min_ev: float = 0.0,
) -> List[EVOpportunity]:
    """Find +EV opportunities by comparing model probs to sportsbook odds.

    Args:
        predictions: {player_name: model_probability}
        odds_by_book: {sportsbook_name: {player_name: american_odds}}
        market: bet market type
        min_ev: minimum EV threshold to include

    Returns:
        List of EVOpportunity sorted by edge descending.
    """
    opportunities = []

    for player, model_prob in predictions.items():
        best_odds = None
        best_book = None

        # Find the best available odds across all sportsbooks
        for book, player_odds in odds_by_book.items():
            if player in player_odds:
                odds = player_odds[player]
                if best_odds is None or odds > best_odds:
                    best_odds = odds
                    best_book = book

        if best_odds is None or best_book is None:
            continue

        implied = american_to_implied_prob(best_odds)
        ev = ev_from_american(model_prob, best_odds)

        if ev >= min_ev:
            opportunities.append(EVOpportunity(
                player=player,
                market=market,
                model_prob=model_prob,
                best_book=best_book,
                best_odds=best_odds,
                implied_prob=implied,
                edge=model_prob - implied,
                ev_per_dollar=ev,
                decimal_odds=american_to_decimal(best_odds),
            ))

    opportunities.sort(key=lambda x: x.edge, reverse=True)
    return opportunities
