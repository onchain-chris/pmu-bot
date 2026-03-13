import sqlite3
from datetime import datetime, timedelta
from contextlib import contextmanager

import config


def get_connection():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY,
                event_id TEXT,
                sport_key TEXT,
                commence_time TEXT,
                horse_name TEXT,
                bookmaker TEXT,
                odds REAL,
                captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS bet_signals (
                id INTEGER PRIMARY KEY,
                event_id TEXT,
                horse_name TEXT,
                pmu_odds REAL,
                fair_prob REAL,
                edge REAL,
                kelly_fraction REAL,
                bet_amount REAL,
                smart_money_signal BOOLEAN,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                result TEXT DEFAULT 'pending',
                profit REAL
            );

            CREATE TABLE IF NOT EXISTS bankroll_log (
                id INTEGER PRIMARY KEY,
                balance REAL,
                logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_snapshots_event_horse
                ON snapshots(event_id, horse_name);
            CREATE INDEX IF NOT EXISTS idx_snapshots_captured
                ON snapshots(captured_at);
            CREATE INDEX IF NOT EXISTS idx_bet_signals_created
                ON bet_signals(created_at);
        """)


def save_snapshot(event_id, sport_key, commence_time, horse_name, bookmaker, odds):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO snapshots
               (event_id, sport_key, commence_time, horse_name, bookmaker, odds)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (event_id, sport_key, commence_time, horse_name, bookmaker, odds),
        )


def save_snapshots_batch(rows):
    """Save multiple snapshot rows at once. Each row is a tuple of
    (event_id, sport_key, commence_time, horse_name, bookmaker, odds)."""
    with get_db() as conn:
        conn.executemany(
            """INSERT INTO snapshots
               (event_id, sport_key, commence_time, horse_name, bookmaker, odds)
               VALUES (?, ?, ?, ?, ?, ?)""",
            rows,
        )


def save_bet_signal(event_id, horse_name, pmu_odds, fair_prob, edge,
                    kelly_fraction, bet_amount, smart_money_signal):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO bet_signals
               (event_id, horse_name, pmu_odds, fair_prob, edge,
                kelly_fraction, bet_amount, smart_money_signal)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_id, horse_name, pmu_odds, fair_prob, edge,
             kelly_fraction, bet_amount, smart_money_signal),
        )


def log_bankroll(balance):
    with get_db() as conn:
        conn.execute("INSERT INTO bankroll_log (balance) VALUES (?)", (balance,))


def get_historical_odds(event_id, horse_name, minutes_ago=None):
    """Get historical odds snapshots for a horse. If minutes_ago is set,
    only return snapshots from that many minutes ago or earlier."""
    with get_db() as conn:
        if minutes_ago is not None:
            cutoff = datetime.utcnow() - timedelta(minutes=minutes_ago)
            rows = conn.execute(
                """SELECT bookmaker, odds, captured_at FROM snapshots
                   WHERE event_id = ? AND horse_name = ? AND captured_at <= ?
                   ORDER BY captured_at DESC""",
                (event_id, horse_name, cutoff.isoformat()),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT bookmaker, odds, captured_at FROM snapshots
                   WHERE event_id = ? AND horse_name = ?
                   ORDER BY captured_at DESC""",
                (event_id, horse_name),
            ).fetchall()
        return [dict(r) for r in rows]


def get_todays_signals():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM bet_signals
               WHERE date(created_at) = ?
               ORDER BY created_at DESC""",
            (today,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_current_bankroll():
    with get_db() as conn:
        row = conn.execute(
            "SELECT balance FROM bankroll_log ORDER BY logged_at DESC LIMIT 1"
        ).fetchone()
        return row["balance"] if row else config.BANKROLL


def get_events_tracked_today():
    today = datetime.utcnow().strftime("%Y-%m-%d")
    with get_db() as conn:
        row = conn.execute(
            """SELECT COUNT(DISTINCT event_id) as cnt FROM snapshots
               WHERE date(captured_at) = ?""",
            (today,),
        ).fetchone()
        return row["cnt"] if row else 0


def get_all_signals(limit=100):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM bet_signals ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_bankroll_history(limit=50):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT balance, logged_at FROM bankroll_log ORDER BY logged_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def update_bankroll(new_balance):
    log_bankroll(new_balance)


def update_signal_result(signal_id, result, profit):
    with get_db() as conn:
        conn.execute(
            "UPDATE bet_signals SET result = ?, profit = ? WHERE id = ?",
            (result, profit, signal_id),
        )
