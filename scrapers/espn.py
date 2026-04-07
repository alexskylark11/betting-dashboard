"""ESPN unofficial API client — leaderboard, field, rankings."""

from typing import Dict, List, Optional
from scrapers.base import ScraperBase
from utils.cache import get_cached, set_cached
from config import ESPN_API_BASE, CACHE_TTL_LIVE, CACHE_TTL_RANKINGS


class ESPNScraper(ScraperBase):
    """Fetches data from ESPN's public API endpoints (no auth required)."""

    def __init__(self):
        super().__init__("espn")

    def get_golf_scoreboard(self) -> Dict:
        """Get current PGA Tour scoreboard with field and scores."""
        cache_key = "espn_golf_scoreboard"
        cached = get_cached(cache_key, CACHE_TTL_LIVE)
        if cached:
            return cached

        self.log.info("Fetching golf scoreboard from ESPN")
        resp = self.get_session().get(f"{ESPN_API_BASE}/golf/pga/scoreboard")
        resp.raise_for_status()
        data = resp.json()
        set_cached(cache_key, data)
        return data

    def get_golf_leaderboard(self) -> List[Dict]:
        """Parse the scoreboard into a clean leaderboard list."""
        scoreboard = self.get_golf_scoreboard()
        leaderboard = []

        for event in scoreboard.get("events", []):
            event_name = event.get("name", "")
            for competition in event.get("competitions", []):
                for competitor in competition.get("competitors", []):
                    athlete = competitor.get("athlete", {})
                    stats = competitor.get("statistics", [])

                    # Parse stats into a clean dict
                    stat_dict = {}
                    for stat in stats:
                        stat_dict[stat.get("name", "")] = stat.get("displayValue", "")

                    entry = {
                        "name": athlete.get("displayName", ""),
                        "espn_id": athlete.get("id", ""),
                        "country": athlete.get("flag", {}).get("alt", ""),
                        "position": competitor.get("status", {}).get("position", {}).get("displayName", ""),
                        "total_score": stat_dict.get("totalPar", stat_dict.get("total", "")),
                        "today": stat_dict.get("todayPar", stat_dict.get("today", "")),
                        "thru": stat_dict.get("thru", ""),
                        "round1": stat_dict.get("R1", ""),
                        "round2": stat_dict.get("R2", ""),
                        "round3": stat_dict.get("R3", ""),
                        "round4": stat_dict.get("R4", ""),
                        "event_name": event_name,
                        "status": competitor.get("status", {}).get("type", {}).get("description", ""),
                    }
                    leaderboard.append(entry)

        # Sort by position (handle non-numeric positions like "CUT")
        def sort_key(x):
            pos = x.get("position", "999")
            if pos.startswith("T"):
                pos = pos[1:]
            try:
                return int(pos)
            except ValueError:
                return 999

        leaderboard.sort(key=sort_key)
        return leaderboard

    def get_golf_rankings(self) -> List[Dict]:
        """Get OWGR world golf rankings."""
        cache_key = "espn_golf_rankings"
        cached = get_cached(cache_key, CACHE_TTL_RANKINGS)
        if cached:
            return cached

        self.log.info("Fetching golf rankings from ESPN")
        resp = self.get_session().get(
            "https://sports.core.api.espn.com/v2/sports/golf/leagues/pga/rankings"
        )
        resp.raise_for_status()
        data = resp.json()

        rankings = []
        for ranking_type in data.get("rankings", []):
            if ranking_type.get("name", "") == "World Golf Ranking":
                for rank_entry in ranking_type.get("ranks", []):
                    athlete_ref = rank_entry.get("athlete", {})
                    rankings.append({
                        "rank": rank_entry.get("current", 0),
                        "name": athlete_ref.get("displayName", ""),
                        "espn_id": athlete_ref.get("id", ""),
                        "previous_rank": rank_entry.get("previous", 0),
                        "points": rank_entry.get("points", 0),
                    })
                break

        set_cached(cache_key, rankings)
        return rankings

    def get_nfl_scoreboard(self, week: Optional[int] = None) -> Dict:
        """Get NFL scoreboard."""
        cache_key = f"espn_nfl_scoreboard_{week or 'current'}"
        cached = get_cached(cache_key, CACHE_TTL_LIVE)
        if cached:
            return cached

        url = f"{ESPN_API_BASE}/football/nfl/scoreboard"
        params = {}
        if week:
            params["week"] = week

        resp = self.get_session().get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        set_cached(cache_key, data)
        return data

    def get_current_tournament_name(self) -> str:
        """Get the name of the current PGA Tour event."""
        scoreboard = self.get_golf_scoreboard()
        for event in scoreboard.get("events", []):
            return event.get("name", "PGA Tour Event")
        return "PGA Tour Event"
