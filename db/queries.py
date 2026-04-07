"""CRUD operations for the betting database."""

import sqlite3
from datetime import datetime
from typing import Optional, List, Dict
from db.models import get_connection


# ── Players ──────────────────────────────────────────────────────────────────

def upsert_player(name: str, sport: str, **kwargs) -> int:
    con = get_connection()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO players (name, sport, espn_id, datagolf_id, world_ranking, country) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(name, sport) DO UPDATE SET "
        "espn_id=COALESCE(excluded.espn_id, players.espn_id), "
        "datagolf_id=COALESCE(excluded.datagolf_id, players.datagolf_id), "
        "world_ranking=COALESCE(excluded.world_ranking, players.world_ranking), "
        "country=COALESCE(excluded.country, players.country)",
        (name, sport, kwargs.get("espn_id"), kwargs.get("datagolf_id"),
         kwargs.get("world_ranking"), kwargs.get("country")),
    )
    con.commit()
    player_id = cur.execute(
        "SELECT id FROM players WHERE name=? AND sport=?", (name, sport)
    ).fetchone()[0]
    con.close()
    return player_id


# ── Odds ─────────────────────────────────────────────────────────────────────

def save_odds_snapshot(player_id: int, event_name: str, market: str,
                       sportsbook: str, american_odds: int,
                       decimal_odds: float, implied_prob: float):
    con = get_connection()
    con.execute(
        "INSERT INTO odds_snapshots "
        "(player_id, event_name, market, sportsbook, american_odds, decimal_odds, implied_prob) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (player_id, event_name, market, sportsbook, american_odds, decimal_odds, implied_prob),
    )
    con.commit()
    con.close()


def get_latest_odds(event_name: str, market: str = "outright") -> List[Dict]:
    """Get latest odds per player per sportsbook for an event."""
    con = get_connection()
    con.row_factory = sqlite3.Row
    rows = con.execute("""
        SELECT p.name, o.sportsbook, o.american_odds, o.decimal_odds,
               o.implied_prob, o.snapshot_at
        FROM odds_snapshots o
        JOIN players p ON p.id = o.player_id
        WHERE o.event_name = ? AND o.market = ?
          AND o.snapshot_at = (
              SELECT MAX(o2.snapshot_at)
              FROM odds_snapshots o2
              WHERE o2.player_id = o.player_id
                AND o2.sportsbook = o.sportsbook
                AND o2.event_name = o.event_name
                AND o2.market = o.market
          )
        ORDER BY o.american_odds ASC
    """, (event_name, market)).fetchall()
    con.close()
    return [dict(r) for r in rows]


# ── Bets & Bankroll ──────────────────────────────────────────────────────────

def get_bankroll_balance() -> float:
    con = get_connection()
    row = con.execute("SELECT balance_after FROM bankroll ORDER BY id DESC LIMIT 1").fetchone()
    con.close()
    return row[0] if row else 0.0


def add_bankroll_entry(action: str, amount: float, bet_id: Optional[int] = None, note: str = ""):
    con = get_connection()
    current = get_bankroll_balance()
    new_balance = current + amount
    con.execute(
        "INSERT INTO bankroll (action, amount, balance_after, bet_id, note) "
        "VALUES (?, ?, ?, ?, ?)",
        (action, amount, new_balance, bet_id, note),
    )
    con.commit()
    con.close()
    return new_balance


def place_bet(player_name: str, sport: str, event_name: str, market: str,
              sportsbook: str, american_odds: int, stake: float,
              model_prob: float = None, ev: float = None) -> int:
    con = get_connection()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO bets (player_name, sport, event_name, market, sportsbook, "
        "american_odds, stake, model_prob, ev_at_placement, result) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')",
        (player_name, sport, event_name, market, sportsbook, american_odds,
         stake, model_prob, ev),
    )
    bet_id = cur.lastrowid
    con.commit()
    con.close()
    add_bankroll_entry("bet_placed", -stake, bet_id, f"{player_name} {market} @ {american_odds}")
    return bet_id


def settle_bet(bet_id: int, result: str, payout: float = 0.0):
    con = get_connection()
    con.execute(
        "UPDATE bets SET result=?, payout=?, settled_at=? WHERE id=?",
        (result, payout, datetime.now().isoformat(), bet_id),
    )
    con.commit()
    con.close()
    if result == "win":
        add_bankroll_entry("bet_won", payout, bet_id)
    elif result == "loss":
        pass  # already deducted on placement


def get_bet_history(sport: Optional[str] = None) -> List[Dict]:
    con = get_connection()
    con.row_factory = sqlite3.Row
    query = "SELECT * FROM bets"
    params = []
    if sport:
        query += " WHERE sport = ?"
        params.append(sport)
    query += " ORDER BY placed_at DESC"
    rows = con.execute(query, params).fetchall()
    con.close()
    return [dict(r) for r in rows]


def get_bankroll_history() -> List[Dict]:
    con = get_connection()
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM bankroll ORDER BY created_at ASC").fetchall()
    con.close()
    return [dict(r) for r in rows]
