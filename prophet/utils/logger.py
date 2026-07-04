import logging
import sqlite3
from datetime import datetime
from rich.logging import RichHandler
from config import DB_PATH, LOG_LEVEL


def get_logger(name: str) -> logging.Logger:
    """Returns a rich-formatted logger."""
    logging.basicConfig(
        level   = getattr(logging, LOG_LEVEL),
        format  = "%(message)s",
        handlers= [RichHandler(rich_tracebacks=True)]
    )
    return logging.getLogger(name)


class TradeLogger:
    """Persists every signal and trade result to SQLite."""

    def __init__(self, db_path: str = DB_PATH):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS prophet_signals (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT,
                asset           TEXT,
                direction       TEXT,
                confidence      REAL,
                at_key_level    INTEGER,
                key_level_type  TEXT,
                current_price   REAL,
                cvd_value       REAL,
                volume_zscore   REAL,
                phase1_pass     INTEGER,
                phase2_pass     INTEGER,
                phase3_pass     INTEGER,
                reason          TEXT
            );

            CREATE TABLE IF NOT EXISTS prophet_trades (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp       TEXT,
                asset           TEXT,
                direction       TEXT,
                stake           REAL,
                duration        INTEGER,
                broker_trade_id TEXT,
                result          TEXT,
                profit          REAL,
                demo            INTEGER,
                signal_id       INTEGER,
                FOREIGN KEY(signal_id) REFERENCES prophet_signals(id)
            );
        """)
        self.conn.commit()

    def log_signal(self, signal) -> int:
        cur = self.conn.execute("""
            INSERT INTO prophet_signals
                (timestamp, asset, direction, confidence, at_key_level,
                 key_level_type, current_price, cvd_value, volume_zscore,
                 phase1_pass, phase2_pass, phase3_pass, reason)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            signal.timestamp.isoformat(),
            signal.asset,
            signal.direction,
            signal.confidence,
            int(signal.at_key_level),
            signal.key_level_type,
            signal.current_price,
            signal.cvd_value,
            signal.volume_zscore,
            int(signal.phase1_pass),
            int(signal.phase2_pass),
            int(signal.phase3_pass),
            signal.reason
        ))
        self.conn.commit()
        return cur.lastrowid

    def log_trade(self, trade, signal_id: int):
        self.conn.execute("""
            INSERT INTO prophet_trades
                (timestamp, asset, direction, stake, duration,
                 broker_trade_id, result, profit, demo, signal_id)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            trade.timestamp.isoformat(),
            trade.asset,
            trade.direction,
            trade.stake,
            trade.duration,
            trade.broker_trade_id,
            trade.result,
            trade.profit,
            int(trade.demo),
            signal_id
        ))
        self.conn.commit()
