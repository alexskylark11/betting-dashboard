"""Real-time data refresh agent.

Fetches ESPN leaderboard, world rankings, and sportsbook odds on a loop,
stores snapshots in SQLite for the dashboard to read.

Usage:
    # One-shot refresh
    python agents/refresh_agent.py

    # Continuous mode — refresh every N minutes
    python agents/refresh_agent.py --loop --interval 10

    # Quiet mode (no table output)
    python agents/refresh_agent.py --loop --interval 10 --quiet
"""

import argparse
import sys
import os
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scrapers.base import setup_logger
from scrapers.espn import ESPNScraper
from scrapers.odds_api import OddsAPIScraper
from db.models import init_db
from db.queries import upsert_player, save_odds_snapshot
from utils.odds_math import american_to_decimal, american_to_implied_prob
from models.golf_model import (
    build_profiles_from_data, monte_carlo_tournament,
    compute_composite_scores, scores_to_probabilities,
)

log = setup_logger("refresh_agent")


# -- ESPN refresh -------------------------------------------------------------

def refresh_espn_leaderboard(espn: ESPNScraper, quiet: bool = False) -> dict:
    """Fetch leaderboard + rankings, upsert players into DB."""
    log.info("Refreshing ESPN leaderboard...")
    leaderboard = espn.get_golf_leaderboard()
    rankings = []
    try:
        rankings = espn.get_golf_rankings()
    except Exception as e:
        log.warning("Could not fetch rankings: %s", e)

    ranking_map = {r["name"]: r.get("rank", 999) for r in rankings}

    event_name = "Unknown"
    player_count = 0

    for entry in leaderboard:
        name = entry.get("name", "")
        if not name:
            continue
        event_name = entry.get("event_name", event_name)
        upsert_player(
            name=name,
            sport="golf",
            espn_id=entry.get("espn_id"),
            world_ranking=ranking_map.get(name),
            country=entry.get("country"),
        )
        player_count += 1

    log.info("ESPN: %d players synced for %s", player_count, event_name)

    if not quiet and leaderboard:
        print(f"\n{'-'*70}")
        print(f"  {event_name} — {datetime.now():%H:%M:%S}")
        print(f"{'-'*70}")
        print(f"  {'Pos':<6} {'Player':<28} {'Score':<8} {'Today':<8} {'Thru':<6}")
        print(f"  {'-'*5} {'-'*27} {'-'*7} {'-'*7} {'-'*5}")
        for p in leaderboard[:20]:
            pos = p.get("position", "")
            name = p.get("name", "")[:27]
            score = p.get("total_score", "")
            today = p.get("today", "")
            thru = p.get("thru", "")
            print(f"  {pos:<6} {name:<28} {score:<8} {today:<8} {thru:<6}")
        if len(leaderboard) > 20:
            print(f"  ... and {len(leaderboard) - 20} more")

    return {
        "event_name": event_name,
        "leaderboard": leaderboard,
        "rankings": rankings,
        "player_count": player_count,
    }


# -- Odds refresh -------------------------------------------------------------

def refresh_odds(odds_api: OddsAPIScraper, quiet: bool = False) -> dict:
    """Fetch outright odds from all sportsbooks, store snapshots."""
    log.info("Refreshing sportsbook odds...")

    odds_by_book = odds_api.get_golf_outright_odds("masters")

    if not odds_by_book:
        log.warning("No odds returned (check API key)")
        return {"books": 0, "players": 0, "snapshots": 0}

    snapshot_count = 0
    all_players = set()

    for book, player_odds in odds_by_book.items():
        for player_name, american_odds in player_odds.items():
            player_id = upsert_player(name=player_name, sport="golf")
            save_odds_snapshot(
                player_id=player_id,
                event_name="Masters Tournament",
                market="outright",
                sportsbook=book,
                american_odds=american_odds,
                decimal_odds=american_to_decimal(american_odds),
                implied_prob=american_to_implied_prob(american_odds),
            )
            all_players.add(player_name)
            snapshot_count += 1

    books = list(odds_by_book.keys())
    log.info("Odds: %d snapshots from %d books for %d players",
             snapshot_count, len(books), len(all_players))

    if not quiet:
        print(f"\n  Sportsbooks: {', '.join(books)}")
        print(f"  Players with odds: {len(all_players)}")
        print(f"  Snapshots stored: {snapshot_count}")
        if odds_api.remaining_credits is not None:
            print(f"  API credits remaining: {odds_api.remaining_credits}")

    return {"books": len(books), "players": len(all_players), "snapshots": snapshot_count}


# -- Model refresh ------------------------------------------------------------

def refresh_model(leaderboard: list, rankings: list, quiet: bool = False) -> dict:
    """Run Monte Carlo simulation and store predictions."""
    if not leaderboard:
        return {"players": 0}

    log.info("Running Monte Carlo simulation (50K sims)...")
    profiles = build_profiles_from_data(leaderboard, rankings)
    mc_results = monte_carlo_tournament(profiles, n_simulations=50000)

    if not quiet:
        # Show top 15 predictions
        sorted_results = sorted(mc_results.items(), key=lambda x: x[1]["win"], reverse=True)
        print(f"\n  {'Player':<28} {'Win':<8} {'Top5':<8} {'Top10':<8} {'Top20':<8}")
        print(f"  {'-'*27} {'-'*7} {'-'*7} {'-'*7} {'-'*7}")
        for name, r in sorted_results[:15]:
            print(f"  {name:<28} {r['win']:>6.2%} {r['top5']:>6.1%} "
                  f"{r['top10']:>6.1%} {r['top20']:>6.1%}")

    return {"players": len(mc_results)}


# -- Main loop ----------------------------------------------------------------

def run_refresh(quiet: bool = False):
    """Execute one full refresh cycle."""
    start = time.time()
    log.info("=" * 50)
    log.info("Starting refresh cycle at %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    espn = ESPNScraper()
    odds_api = OddsAPIScraper()

    # 1. ESPN data
    espn_result = refresh_espn_leaderboard(espn, quiet)

    # 2. Sportsbook odds
    odds_result = refresh_odds(odds_api, quiet)

    # 3. Model predictions
    model_result = refresh_model(
        espn_result["leaderboard"],
        espn_result["rankings"],
        quiet,
    )

    elapsed = time.time() - start
    log.info("Refresh complete in %.1fs", elapsed)

    if not quiet:
        print(f"\n{'-'*70}")
        print(f"  Refresh complete in {elapsed:.1f}s")
        print(f"  Players: {espn_result['player_count']} | "
              f"Books: {odds_result['books']} | "
              f"Odds snapshots: {odds_result['snapshots']}")
        print(f"{'-'*70}\n")

    return {
        "espn": espn_result,
        "odds": odds_result,
        "model": model_result,
        "elapsed": elapsed,
    }


def main():
    parser = argparse.ArgumentParser(description="Betting dashboard data refresh agent")
    parser.add_argument("--loop", action="store_true", help="Run continuously")
    parser.add_argument("--interval", type=int, default=10, help="Minutes between refreshes (default: 10)")
    parser.add_argument("--quiet", action="store_true", help="Suppress table output")
    args = parser.parse_args()

    init_db()

    if args.loop:
        log.info("Starting continuous refresh (every %d min). Ctrl+C to stop.", args.interval)
        print(f"\n  Refresh agent running every {args.interval} minutes. Ctrl+C to stop.\n")
        cycle = 0
        while True:
            cycle += 1
            log.info("Cycle %d", cycle)
            try:
                run_refresh(quiet=args.quiet)
            except Exception as e:
                log.error("Refresh failed: %s", e)
            log.info("Sleeping %d minutes...", args.interval)
            time.sleep(args.interval * 60)
    else:
        run_refresh(quiet=args.quiet)


if __name__ == "__main__":
    main()
