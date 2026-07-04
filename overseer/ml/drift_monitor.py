from __future__ import annotations

import json
import logging
import os
import sqlite3
from typing import Any

LOGGER = logging.getLogger("overseer.drift_monitor")

_DRIFT_CHECK_INTERVAL_TICKS = int(os.getenv("DRIFT_CHECK_INTERVAL_TICKS", "500"))
_DRIFT_MIN_SAMPLE = int(os.getenv("DRIFT_MIN_SAMPLE", "20"))
_DRIFT_WR_DROP_THRESHOLD = float(os.getenv("DRIFT_WR_DROP_THRESHOLD", "30.0"))
_DRIFT_AUTO_DISABLE = os.getenv("DRIFT_AUTO_DISABLE", "true").lower() == "true"

_SCORE_BUCKETS = [
    (0.80, 0.85),
    (0.85, 0.90),
    (0.90, 0.95),
    (0.95, 1.01),
]

_EXPECTED_WR = {
    (0.80, 0.85): 92.0,
    (0.85, 0.90): 95.6,
    (0.90, 0.95): 100.0,
    (0.95, 1.01): 100.0,
}


class DriftMonitor:
    def __init__(self) -> None:
        self._last_check_tick = 0
        self._drift_detected = False
        self._drift_details: dict[str, Any] = {}
        self._trading_disabled = False

    def should_check(self, tick_count: int) -> bool:
        return (tick_count - self._last_check_tick) >= _DRIFT_CHECK_INTERVAL_TICKS

    def check(
        self,
        conn: sqlite3.Connection,
        tick_count: int,
    ) -> dict[str, Any]:
        self._last_check_tick = tick_count
        results: dict[str, Any] = {"buckets": {}, "drift": False, "action": "none"}

        for bucket_lo, bucket_hi in _SCORE_BUCKETS:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COALESCE(SUM(CASE WHEN outcome_200ticks = 'WIN' THEN 1 ELSE 0 END), 0) AS wins
                FROM signal_log
                WHERE score >= ? AND score < ?
                AND outcome_200ticks IS NOT NULL
                AND outcome_200ticks != 'FLAT'
                AND timestamp >= datetime('now', '-24 hours')
                """,
                (bucket_lo, bucket_hi),
            ).fetchone()

            total = row[0] if row else 0
            wins = row[1] if row else 0
            actual_wr = (wins / total * 100) if total > 0 else None
            expected_wr = _EXPECTED_WR.get((bucket_lo, bucket_hi), 0)

            bucket_key = f"{bucket_lo:.2f}-{bucket_hi:.2f}"
            results["buckets"][bucket_key] = {
                "total": total,
                "wins": wins,
                "actual_wr": round(actual_wr, 1) if actual_wr is not None else None,
                "expected_wr": expected_wr,
                "drift": False,
            }

            if actual_wr is not None and total >= _DRIFT_MIN_SAMPLE:
                drop = expected_wr - actual_wr
                if drop > _DRIFT_WR_DROP_THRESHOLD:
                    results["buckets"][bucket_key]["drift"] = True
                    results["drift"] = True
                    results["drift_bucket"] = bucket_key
                    results["actual_wr"] = round(actual_wr, 1)
                    results["expected_wr"] = expected_wr
                    results["drop_pp"] = round(drop, 1)

        for symbol in ("6BM6", "6AM6", "6CM6", "6EM6", "6JM6"):
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COALESCE(SUM(CASE WHEN outcome_200ticks = 'WIN' THEN 1 ELSE 0 END), 0) AS wins
                FROM signal_log
                WHERE symbol = ? AND score >= 0.85
                AND outcome_200ticks IS NOT NULL
                AND outcome_200ticks != 'FLAT'
                AND timestamp >= datetime('now', '-24 hours')
                """,
                (symbol,),
            ).fetchone()
            total = row[0] if row else 0
            wins = row[1] if row else 0
            actual_wr = (wins / total * 100) if total > 0 else None
            results[f"symbol_{symbol}"] = {
                "total": total,
                "actual_wr": round(actual_wr, 1) if actual_wr is not None else None,
            }

        for direction in ("BUY", "SELL"):
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COALESCE(SUM(CASE WHEN outcome_200ticks = 'WIN' THEN 1 ELSE 0 END), 0) AS wins
                FROM signal_log
                WHERE direction = ? AND score >= 0.85
                AND outcome_200ticks IS NOT NULL
                AND outcome_200ticks != 'FLAT'
                AND timestamp >= datetime('now', '-24 hours')
                """,
                (direction,),
            ).fetchone()
            total = row[0] if row else 0
            wins = row[1] if row else 0
            actual_wr = (wins / total * 100) if total > 0 else None
            results[f"direction_{direction}"] = {
                "total": total,
                "actual_wr": round(actual_wr, 1) if actual_wr is not None else None,
            }

        if results["drift"]:
            self._drift_detected = True
            self._drift_details = results
            if _DRIFT_AUTO_DISABLE:
                self._trading_disabled = True
                results["action"] = "trading_disabled"
            else:
                results["action"] = "drift_alert"
            LOGGER.warning(
                "Model drift detected! Bucket %s: expected %.1f%% WR, actual %.1f%% WR (drop=%.1fpp)",
                results.get("drift_bucket", "?"),
                results.get("expected_wr", 0),
                results.get("actual_wr", 0),
                results.get("drop_pp", 0),
            )
        else:
            self._drift_detected = False
            self._trading_disabled = False

        return results

    def is_trading_allowed(self) -> tuple[bool, str]:
        if self._trading_disabled:
            return False, f"Model drift detected: {self._drift_details.get('drift_bucket', 'unknown')}"
        return True, ""

    def get_status(self) -> dict[str, Any]:
        return {
            "drift_detected": self._drift_detected,
            "trading_disabled": self._trading_disabled,
            "details": self._drift_details,
        }

    def reset(self) -> None:
        self._drift_detected = False
        self._trading_disabled = False
        self._drift_details = {}
