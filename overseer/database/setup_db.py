from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "overseer_trades.db"


_DB_DAILY_LOSS_LIMIT = float(os.getenv("DB_DAILY_LOSS_LIMIT", "500"))
_DB_CONSECUTIVE_LOSSES = int(os.getenv("DB_CONSECUTIVE_LOSSES", "2"))

SCHEMA = f"""
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS system_status (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    is_halted INTEGER NOT NULL DEFAULT 0 CHECK (is_halted IN (0, 1)),
    halt_reason TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    event_log TEXT
);

INSERT OR IGNORE INTO system_status (id, is_halted, halt_reason, updated_at, event_log)
VALUES (1, 0, NULL, datetime('now'), 'SYSTEM_INITIALIZED');

CREATE TABLE IF NOT EXISTS trade_executions (
    trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('BUY', 'SELL')),
    entry_price REAL NOT NULL,
    exit_price REAL,
    pnl REAL NOT NULL DEFAULT 0,
    gate_states_json TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tick_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    bid REAL NOT NULL,
    ask REAL NOT NULL,
    delta REAL NOT NULL,
    dom_json TEXT NOT NULL,
    timestamp INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS model_features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER,
    symbol TEXT NOT NULL,
    bid REAL,
    ask REAL,
    spread REAL,
    delta REAL,
    mid_price REAL,
    pnl REAL NOT NULL DEFAULT 0,
    gate_states_json TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (trade_id) REFERENCES trade_executions(trade_id)
);

CREATE TABLE IF NOT EXISTS candle_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    open_time TEXT NOT NULL,
    close_time TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL DEFAULT 0,
    tick_count INTEGER NOT NULL DEFAULT 0,
    ema_20 REAL,
    ema_50 REAL,
    rsi_14 REAL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_candle_sym_tf_time
    ON candle_history(symbol, timeframe, open_time);

CREATE TABLE IF NOT EXISTS economic_calendar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_name TEXT NOT NULL,
    currency TEXT NOT NULL,
    impact TEXT NOT NULL CHECK (impact IN ('low', 'medium', 'high')),
    forecast REAL,
    previous REAL,
    actual REAL,
    timestamp_utc TEXT NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'unknown'
);

CREATE INDEX IF NOT EXISTS idx_econ_cal_currency_ts
    ON economic_calendar(currency, timestamp_ms);

CREATE TABLE IF NOT EXISTS economic_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_name TEXT NOT NULL,
    currency TEXT NOT NULL,
    date TEXT NOT NULL,
    forecast REAL,
    actual REAL,
    previous REAL,
    surprise_pct REAL,
    direction_impact TEXT
);

CREATE INDEX IF NOT EXISTS idx_econ_hist_event_currency
    ON economic_history(event_name, currency);

CREATE TABLE IF NOT EXISTS signal_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        direction TEXT NOT NULL CHECK (direction IN ('BUY', 'SELL')),
        score REAL NOT NULL,
        adjusted_score REAL NOT NULL,
        executed INTEGER NOT NULL DEFAULT 0 CHECK (executed IN (0, 1)),
        entry_price REAL,
        exit_price REAL,
        pnl REAL,
        close_reason TEXT,
        gate_states_json TEXT NOT NULL,
        framework_scores_json TEXT,
        l3_features_json TEXT,
        bias_breakdown_json TEXT,
        dom_snapshot_json TEXT,
        tick_bid REAL,
        tick_ask REAL,
        tick_delta REAL,
        tick_volume REAL,
        spread_bps REAL,
        risk_regime TEXT,
        session TEXT,
        dxy REAL,
        source TEXT DEFAULT 'live',
        outcome_10ticks TEXT,
        outcome_50ticks TEXT,
        outcome_200ticks TEXT,
        timestamp TEXT NOT NULL DEFAULT (datetime('now')),
        closed_at TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_signal_log_symbol
    ON signal_log(symbol, timestamp DESC);

    CREATE INDEX IF NOT EXISTS idx_signal_log_executed
    ON signal_log(executed, timestamp DESC);

CREATE TABLE IF NOT EXISTS cot_positioning (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    report_date TEXT NOT NULL,
    large_spec_long REAL,
    large_spec_short REAL,
    large_spec_net REAL,
    retail_long_pct REAL,
    retail_short_pct REAL,
    source TEXT NOT NULL DEFAULT 'unknown',
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cot_sym_date
    ON cot_positioning(symbol, report_date);

CREATE TABLE IF NOT EXISTS options_iv (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol           TEXT    NOT NULL,
    currency         TEXT,
    atm_iv           REAL,
    rr_25d           REAL,
    rr_10d           REAL,
    butterfly_25d    REAL,
    iv_percentile_52w REAL,
    skew_score       INTEGER,
    source           TEXT    NOT NULL DEFAULT 'unknown',
    scraped_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(symbol, scraped_at)
);

    CREATE INDEX IF NOT EXISTS idx_options_iv_symbol
    ON options_iv(symbol, scraped_at DESC);

    CREATE TABLE IF NOT EXISTS yahoo_news (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        currency TEXT NOT NULL,
        sentiment_score REAL DEFAULT 0,
        headline_count INTEGER DEFAULT 0,
        bullish_count INTEGER DEFAULT 0,
        bearish_count INTEGER DEFAULT 0,
        fetched_at TEXT NOT NULL,
        UNIQUE(currency, fetched_at)
    );

    CREATE INDEX IF NOT EXISTS idx_yahoo_news_currency
    ON yahoo_news(currency, fetched_at DESC);

    CREATE TABLE IF NOT EXISTS cboe_fx_vol (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        currency TEXT NOT NULL,
        ticker TEXT,
        iv_value REAL,
        iv_change REAL DEFAULT 0,
        source TEXT DEFAULT 'rapidapi',
        fetch_date TEXT,
        fetched_at TEXT,
        UNIQUE(currency, fetch_date)
    );

    CREATE INDEX IF NOT EXISTS idx_cboe_fx_vol_currency
    ON cboe_fx_vol(currency, fetch_date DESC);

    CREATE TABLE IF NOT EXISTS cot_reports_lib (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        instrument TEXT NOT NULL,
        report_date TEXT,
        noncomm_long INTEGER,
        noncomm_short INTEGER,
        net_position INTEGER,
        zscore REAL,
        source TEXT DEFAULT 'cftc_direct',
        fetched_at TEXT,
        UNIQUE(instrument, report_date)
    );

    CREATE INDEX IF NOT EXISTS idx_cot_reports_lib_instrument
    ON cot_reports_lib(instrument, report_date DESC);

    CREATE TABLE IF NOT EXISTS fxssi_sentiment (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pair TEXT NOT NULL,
        buy_pct REAL,
        sell_pct REAL,
        signal TEXT,
        fetched_at TEXT NOT NULL,
        UNIQUE(pair, fetched_at)
    );

    CREATE INDEX IF NOT EXISTS idx_fxssi_sentiment_pair
    ON fxssi_sentiment(pair, fetched_at DESC);

CREATE TRIGGER IF NOT EXISTS trg_trade_risk_halt
AFTER INSERT ON trade_executions
BEGIN
    UPDATE system_status
    SET
        is_halted = CASE
            WHEN (
                SELECT COALESCE(SUM(pnl), 0)
                FROM trade_executions
                WHERE date(timestamp) = date(NEW.timestamp)
                  AND exit_price IS NOT NULL
            ) < -{_DB_DAILY_LOSS_LIMIT} THEN 1
            WHEN (
                WITH ordered AS (
                    SELECT pnl
                    FROM trade_executions
                    WHERE exit_price IS NOT NULL
                    ORDER BY timestamp DESC, trade_id DESC
                    LIMIT {_DB_CONSECUTIVE_LOSSES}
                )
                SELECT COUNT(*) = {_DB_CONSECUTIVE_LOSSES} AND SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) = {_DB_CONSECUTIVE_LOSSES}
                FROM ordered
            ) THEN 1
            ELSE is_halted
        END,
        halt_reason = CASE
            WHEN (
                SELECT COALESCE(SUM(pnl), 0)
                FROM trade_executions
                WHERE date(timestamp) = date(NEW.timestamp)
                  AND exit_price IS NOT NULL
            ) < -{_DB_DAILY_LOSS_LIMIT} THEN 'DAILY_LOSS_LIMIT'
            WHEN (
                WITH ordered AS (
                    SELECT pnl
                    FROM trade_executions
                    WHERE exit_price IS NOT NULL
                    ORDER BY timestamp DESC, trade_id DESC
                    LIMIT {_DB_CONSECUTIVE_LOSSES}
                )
                SELECT COUNT(*) = {_DB_CONSECUTIVE_LOSSES} AND SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) = {_DB_CONSECUTIVE_LOSSES}
                FROM ordered
            ) THEN 'CONSECUTIVE_LOSS_LIMIT'
            ELSE halt_reason
        END,
        updated_at = datetime('now'),
        event_log = CASE
            WHEN (
                SELECT COALESCE(SUM(pnl), 0)
                FROM trade_executions
                WHERE date(timestamp) = date(NEW.timestamp)
                  AND exit_price IS NOT NULL
            ) < -{_DB_DAILY_LOSS_LIMIT} THEN 'TRIGGER_FIRED:DAILY_LOSS_LIMIT'
            WHEN (
                WITH ordered AS (
                    SELECT pnl
                    FROM trade_executions
                    WHERE exit_price IS NOT NULL
                    ORDER BY timestamp DESC, trade_id DESC
                    LIMIT {_DB_CONSECUTIVE_LOSSES}
                )
                SELECT COUNT(*) = {_DB_CONSECUTIVE_LOSSES} AND SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) = {_DB_CONSECUTIVE_LOSSES}
                FROM ordered
            ) THEN 'TRIGGER_FIRED:CONSECUTIVE_LOSS_LIMIT'
            ELSE 'TRIGGER_EVALUATED:NO_HALT'
        END
    WHERE id = 1;
END;

CREATE TRIGGER IF NOT EXISTS trg_trade_closed_features
AFTER UPDATE OF exit_price ON trade_executions
WHEN NEW.exit_price IS NOT NULL AND OLD.exit_price IS NULL
BEGIN
    INSERT INTO model_features (trade_id, symbol, pnl, gate_states_json, timestamp)
    VALUES (
        NEW.trade_id,
        NEW.symbol,
        NEW.pnl,
        NEW.gate_states_json,
        COALESCE(NEW.closed_at, datetime('now'))
    );
END;
"""


def _add_columns_if_missing(conn: sqlite3.Connection) -> None:
    """Safely add new columns to existing tables (idempotent)."""
    _ALTER_STATEMENTS = [
        "ALTER TABLE trade_executions ADD COLUMN closed_at TEXT",
        "ALTER TABLE trade_executions ADD COLUMN close_reason TEXT",
        "ALTER TABLE signal_log ADD COLUMN outcome_10ticks TEXT",
        "ALTER TABLE signal_log ADD COLUMN outcome_50ticks TEXT",
        "ALTER TABLE signal_log ADD COLUMN outcome_200ticks TEXT",
        "ALTER TABLE signal_log ADD COLUMN closed_at TEXT",
        "ALTER TABLE signal_log ADD COLUMN dom_snapshot_json TEXT",
        "ALTER TABLE signal_log ADD COLUMN dxy REAL",
        "ALTER TABLE signal_log ADD COLUMN risk_regime TEXT",
        "ALTER TABLE signal_log ADD COLUMN session TEXT",
    ]
    for stmt in _ALTER_STATEMENTS:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass  # Column already exists


def init_db(db_path: Path = DB_PATH) -> Path:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path, timeout=10.0, isolation_level="IMMEDIATE") as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA)
        _add_columns_if_missing(conn)
        conn.commit()
    return db_path


def get_runtime_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Get a production-grade runtime DB connection with WAL safeguards."""
    conn = sqlite3.connect(str(db_path), timeout=10.0, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def check_halt_status(db_path: Path = DB_PATH) -> bool:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT is_halted FROM system_status WHERE id = 1").fetchone()
    return bool(row and row[0])


if __name__ == "__main__":
    path = init_db()
    print(f"SQLite database initialized: {path}")
