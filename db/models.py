import sqlite3
import os
from config import DB_PATH


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    con = get_connection()
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            sport TEXT NOT NULL,          -- golf, nfl, horse_racing
            espn_id TEXT,
            datagolf_id TEXT,
            world_ranking INTEGER,
            country TEXT,
            UNIQUE(name, sport)
        );

        CREATE TABLE IF NOT EXISTS odds_snapshots (
            id INTEGER PRIMARY KEY,
            player_id INTEGER REFERENCES players(id),
            event_name TEXT NOT NULL,
            market TEXT NOT NULL,          -- outright, top5, top10, top20, h2h, make_cut
            sportsbook TEXT NOT NULL,
            american_odds INTEGER NOT NULL,
            decimal_odds REAL NOT NULL,
            implied_prob REAL NOT NULL,
            snapshot_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_odds_event_market
            ON odds_snapshots(event_name, market, snapshot_at);
        CREATE INDEX IF NOT EXISTS idx_odds_player
            ON odds_snapshots(player_id, event_name);

        CREATE TABLE IF NOT EXISTS model_predictions (
            id INTEGER PRIMARY KEY,
            player_id INTEGER REFERENCES players(id),
            event_name TEXT NOT NULL,
            market TEXT NOT NULL,
            model_prob REAL NOT NULL,
            ev REAL,
            kelly_fraction REAL,
            computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS golf_stats (
            id INTEGER PRIMARY KEY,
            player_id INTEGER REFERENCES players(id),
            season INTEGER,
            sg_total REAL,
            sg_off_tee REAL,
            sg_approach REAL,
            sg_around_green REAL,
            sg_putting REAL,
            sg_tee_to_green REAL,
            rounds_played INTEGER,
            scoring_avg REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(player_id, season)
        );

        CREATE TABLE IF NOT EXISTS course_history (
            id INTEGER PRIMARY KEY,
            player_id INTEGER REFERENCES players(id),
            course TEXT NOT NULL,
            year INTEGER NOT NULL,
            finish_position INTEGER,
            total_score INTEGER,
            rounds_completed INTEGER,
            made_cut BOOLEAN,
            UNIQUE(player_id, course, year)
        );

        CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY,
            player_name TEXT NOT NULL,
            sport TEXT NOT NULL,
            event_name TEXT NOT NULL,
            market TEXT NOT NULL,
            sportsbook TEXT NOT NULL,
            american_odds INTEGER NOT NULL,
            stake REAL NOT NULL,
            model_prob REAL,
            ev_at_placement REAL,
            result TEXT,                  -- win, loss, push, pending
            payout REAL,
            placed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            settled_at TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS bankroll (
            id INTEGER PRIMARY KEY,
            action TEXT NOT NULL,          -- deposit, withdrawal, bet_placed, bet_won, bet_lost
            amount REAL NOT NULL,
            balance_after REAL NOT NULL,
            bet_id INTEGER REFERENCES bets(id),
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    con.commit()
    con.close()
