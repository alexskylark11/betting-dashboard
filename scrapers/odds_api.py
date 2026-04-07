"""The Odds API client — fetches odds across sportsbooks."""

from typing import Dict, List, Optional
from scrapers.base import ScraperBase
from utils.cache import get_cached, set_cached
from config import ODDS_API_KEY, ODDS_API_BASE, CACHE_TTL_ODDS


class OddsAPIScraper(ScraperBase):
    """Fetches odds from The Odds API (free tier: 500 req/month)."""

    # Sport keys for The Odds API
    SPORT_KEYS = {
        "masters": "golf_masters_tournament_winner",
        "pga": "golf_pga_championship_winner",
        "us_open_golf": "golf_us_open_winner",
        "the_open": "golf_the_open_championship_winner",
        "nfl_spreads": "americanfootball_nfl",
        "nfl_super_bowl": "americanfootball_nfl_super_bowl_winner",
    }

    def __init__(self):
        super().__init__("odds_api")
        self.api_key = ODDS_API_KEY
        self.remaining_credits = None

    def get_sports(self) -> List[Dict]:
        """List all available sports/events."""
        cache_key = "odds_api_sports"
        cached = get_cached(cache_key, CACHE_TTL_ODDS)
        if cached:
            return cached

        resp = self.get_session().get(
            f"{ODDS_API_BASE}/sports",
            params={"apiKey": self.api_key},
        )
        resp.raise_for_status()
        self._track_credits(resp)
        data = resp.json()
        set_cached(cache_key, data)
        return data

    def get_odds(
        self,
        sport_key: str,
        regions: str = "us",
        markets: str = "h2h",
        odds_format: str = "american",
    ) -> List[Dict]:
        """Fetch odds for a sport/event.

        Args:
            sport_key: API sport key (use SPORT_KEYS or get_sports())
            regions: 'us', 'us,eu', etc.
            markets: 'h2h' (moneyline), 'spreads', 'totals'
            odds_format: 'american' or 'decimal'
        """
        cache_key = f"odds_{sport_key}_{regions}_{markets}"
        cached = get_cached(cache_key, CACHE_TTL_ODDS)
        if cached:
            self.log.info("Using cached odds for %s", sport_key)
            return cached

        if not self.api_key:
            self.log.warning("No ODDS_API_KEY set — returning empty")
            return []

        self.log.info("Fetching odds: %s (markets=%s)", sport_key, markets)
        resp = self.get_session().get(
            f"{ODDS_API_BASE}/sports/{sport_key}/odds",
            params={
                "apiKey": self.api_key,
                "regions": regions,
                "markets": markets,
                "oddsFormat": odds_format,
            },
        )
        resp.raise_for_status()
        self._track_credits(resp)
        data = resp.json()
        set_cached(cache_key, data)
        return data

    def get_golf_outright_odds(self, event: str = "masters") -> Dict[str, Dict[str, int]]:
        """Fetch golf outright winner odds, return {sportsbook: {player: american_odds}}.

        Returns dict ready for ev_calculator.find_ev_bets().
        """
        sport_key = self.SPORT_KEYS.get(event, event)
        # Golf uses "outrights" market; team sports use "h2h"
        market_type = "outrights" if "golf" in sport_key else "h2h"
        raw = self.get_odds(sport_key, markets=market_type)

        odds_by_book: Dict[str, Dict[str, int]] = {}

        for event_data in raw:
            for bookmaker in event_data.get("bookmakers", []):
                book_name = bookmaker.get("title", bookmaker.get("key", "unknown"))
                for market in bookmaker.get("markets", []):
                    for outcome in market.get("outcomes", []):
                        player = outcome.get("name", "")
                        price = outcome.get("price", 0)
                        if player and price:
                            if book_name not in odds_by_book:
                                odds_by_book[book_name] = {}
                            odds_by_book[book_name][player] = price

        self.log.info(
            "Parsed odds: %d books, %d players",
            len(odds_by_book),
            len(set().union(*(b.keys() for b in odds_by_book.values())) if odds_by_book else set()),
        )
        return odds_by_book

    def _track_credits(self, resp):
        remaining = resp.headers.get("x-requests-remaining")
        used = resp.headers.get("x-requests-used")
        if remaining:
            self.remaining_credits = int(remaining)
            self.log.info("API credits: %s remaining, %s used", remaining, used)
