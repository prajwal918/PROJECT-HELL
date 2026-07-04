from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("overseer.execution_quality")

_DB_PATH = Path(__file__).resolve().parent.parent / "database" / "overseer_trades.db"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS execution_quality (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket INTEGER,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    lot_size REAL NOT NULL,
    requested_price REAL NOT NULL,
    fill_price REAL NOT NULL,
    slippage_pips REAL NOT NULL,
    spread_at_entry REAL,
    fill_latency_ms REAL,
    rejection_reason TEXT,
    retcode INTEGER,
    score REAL,
    raw_score REAL,
    adjusted_score REAL,
    pipeline_latency_ms REAL,
    gate_eval_ms REAL,
    model_inference_ms REAL,
    risk_check_ms REAL,
    queue_depth_at_entry REAL,
    l3_spoof_signal REAL,
    l3_adverse_risk REAL,
    dom_health TEXT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_exec_quality_symbol
ON execution_quality(symbol, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_exec_quality_ticket
ON execution_quality(ticket);
"""


class ExecutionQualityLogger:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = Path(db_path) if db_path else _DB_PATH
        self._ensure_table()

    def _ensure_table(self) -> None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.executescript(_CREATE_TABLE)
                conn.commit()
        except Exception as exc:
            LOGGER.error("Failed to create execution_quality table: %s", exc)

    def log_fill(
        self,
        symbol: str,
        direction: str,
        lot_size: float,
        requested_price: float,
        fill_price: float,
        slippage_pips: float,
        spread_at_entry: float = 0,
        fill_latency_ms: float = 0,
        ticket: int | None = None,
        retcode: int | None = None,
        score: float = 0,
        raw_score: float = 0,
        adjusted_score: float = 0,
        pipeline_latency_ms: float = 0,
        gate_eval_ms: float = 0,
        model_inference_ms: float = 0,
        risk_check_ms: float = 0,
        queue_depth_at_entry: float = 0,
        l3_spoof_signal: float = 0,
        l3_adverse_risk: float = 0,
        dom_health: str = "unknown",
    ) -> None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO execution_quality
                    (ticket, symbol, direction, lot_size, requested_price, fill_price,
                     slippage_pips, spread_at_entry, fill_latency_ms, retcode,
                     score, raw_score, adjusted_score,
                     pipeline_latency_ms, gate_eval_ms, model_inference_ms, risk_check_ms,
                     queue_depth_at_entry, l3_spoof_signal, l3_adverse_risk, dom_health)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ticket, symbol, direction, lot_size, requested_price, fill_price,
                        slippage_pips, spread_at_entry, fill_latency_ms, retcode,
                        score, raw_score, adjusted_score,
                        pipeline_latency_ms, gate_eval_ms, model_inference_ms, risk_check_ms,
                        queue_depth_at_entry, l3_spoof_signal, l3_adverse_risk, dom_health,
                    ),
                )
                conn.commit()
        except Exception as exc:
            LOGGER.error("Failed to log execution quality: %s", exc)

    def log_rejection(
        self,
        symbol: str,
        direction: str,
        lot_size: float,
        rejection_reason: str,
        requested_price: float = 0,
        spread_at_entry: float = 0,
        score: float = 0,
        raw_score: float = 0,
    ) -> None:
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO execution_quality
                    (ticket, symbol, direction, lot_size, requested_price, fill_price,
                     slippage_pips, spread_at_entry, rejection_reason, score, raw_score)
                    VALUES (NULL, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?)
                    """,
                    (symbol, direction, lot_size, requested_price, spread_at_entry, rejection_reason, score, raw_score),
                )
                conn.commit()
        except Exception as exc:
            LOGGER.error("Failed to log execution rejection: %s", exc)

    def get_fill_stats(self, hours: int = 24, symbol: str | None = None) -> dict[str, Any]:
        try:
            with sqlite3.connect(self._db_path) as conn:
                query = """
                    SELECT
                        COUNT(*) AS fills,
                        AVG(slippage_pips) AS avg_slippage,
                        MAX(slippage_pips) AS max_slippage,
                        AVG(fill_latency_ms) AS avg_fill_latency,
                        MAX(fill_latency_ms) AS max_fill_latency,
                        AVG(spread_at_entry) AS avg_spread,
                        AVG(pipeline_latency_ms) AS avg_pipeline_latency,
                        SUM(CASE WHEN rejection_reason IS NOT NULL THEN 1 ELSE 0 END) AS rejections
                    FROM execution_quality
                    WHERE timestamp >= datetime('now', ?)
                """
                params: list[Any] = [f"-{hours} hours"]
                if symbol:
                    query += " AND symbol = ?"
                    params.append(symbol)

                row = conn.execute(query, params).fetchone()
                if row is None:
                    return {"fills": 0}

                return {
                    "fills": row[0],
                    "avg_slippage_pips": round(row[1], 2) if row[1] else 0,
                    "max_slippage_pips": round(row[2], 2) if row[2] else 0,
                    "avg_fill_latency_ms": round(row[3], 1) if row[3] else 0,
                    "max_fill_latency_ms": round(row[4], 1) if row[4] else 0,
                    "avg_spread": round(row[5], 2) if row[5] else 0,
                    "avg_pipeline_latency_ms": round(row[6], 1) if row[6] else 0,
                    "rejections": row[7],
                }
        except Exception as exc:
            LOGGER.error("Failed to get fill stats: %s", exc)
            return {"fills": 0, "error": str(exc)}

    def get_rejection_breakdown(self, hours: int = 24) -> dict[str, int]:
        try:
            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT rejection_reason, COUNT(*) AS cnt
                    FROM execution_quality
                    WHERE rejection_reason IS NOT NULL
                    AND timestamp >= datetime('now', ?)
                    GROUP BY rejection_reason
                    ORDER BY cnt DESC
                    """,
                    (f"-{hours} hours",),
                ).fetchall()
                return {row[0]: row[1] for row in rows}
        except Exception as exc:
            LOGGER.error("Failed to get rejection breakdown: %s", exc)
            return {}

    def get_slippage_by_symbol(self, hours: int = 24) -> dict[str, dict[str, float]]:
        try:
            with sqlite3.connect(self._db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT symbol,
                           AVG(slippage_pips),
                           MAX(slippage_pips),
                           AVG(spread_at_entry),
                           COUNT(*)
                    FROM execution_quality
                    WHERE fill_price > 0
                    AND timestamp >= datetime('now', ?)
                    GROUP BY symbol
                    """,
                    (f"-{hours} hours",),
                ).fetchall()
                return {
                    row[0]: {
                        "avg_slippage": round(row[1], 2),
                        "max_slippage": round(row[2], 2),
                        "avg_spread": round(row[3], 2),
                        "fills": row[4],
                    }
                    for row in rows
                }
        except Exception as exc:
            LOGGER.error("Failed to get slippage by symbol: %s", exc)
            return {}

    def get_status(self) -> dict[str, Any]:
        stats_24h = self.get_fill_stats(hours=24)
        rejections = self.get_rejection_breakdown(hours=24)
        by_symbol = self.get_slippage_by_symbol(hours=24)
        return {
            "last_24h": stats_24h,
            "rejection_breakdown": rejections,
            "slippage_by_symbol": by_symbol,
        }
