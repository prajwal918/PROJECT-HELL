#!/usr/bin/env python3
"""
Dynamic Threshold Engine v1.0

Auto-discovers the optimal score threshold per symbol+direction
that maximizes win rate while maintaining minimum signal volume.

Scans signal_log outcomes every 5 minutes and finds the threshold
where WR is highest with at least N non-FLAT outcomes.

No hardcodes. Pure data-driven.
"""

import json
import logging
import os
import sqlite3
import time
from typing import Any, Dict, Optional, Tuple

LOGGER = logging.getLogger("overseer.dynamic_threshold")

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "database", "overseer_trades.db"
)

_MIN_NONFLAT = int(os.getenv("DYN_THRESH_MIN_NONFLAT", "20"))
_MIN_WR = float(os.getenv("DYN_THRESH_MIN_WR", "0.90"))
_TARGET_WR = float(os.getenv("DYN_THRESH_TARGET_WR", "0.95"))
_SCAN_STEP = float(os.getenv("DYN_THRESH_SCAN_STEP", "0.01"))
_CACHE_TTL = float(os.getenv("DYN_THRESH_CACHE_TTL", "300"))

_cache: Dict[str, Any] = {}
_cache_ts: float = 0.0


def _get_conn() -> Optional[sqlite3.Connection]:
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception:
        return None


def _scan_threshold(
    conn: sqlite3.Connection, symbol: str, direction: str
) -> Optional[dict]:
    best_thresh = 0.80
    best_wr = 0.0
    best_n = 0
    best_w = 0
    best_l = 0
    found = False

    for step in range(0, 21):
        thresh = 0.80 + step * _SCAN_STEP
        row = conn.execute(
            """
            SELECT
                SUM(CASE WHEN outcome_200ticks='WIN' THEN 1 ELSE 0 END) as w,
                SUM(CASE WHEN outcome_200ticks='LOSS' THEN 1 ELSE 0 END) as l
            FROM signal_log
            WHERE symbol=? AND direction=? AND score >= ?
              AND outcome_200ticks IS NOT NULL
              AND outcome_200ticks != 'FLAT'
            """,
            (symbol, direction, thresh),
        ).fetchone()
        w = row["w"] or 0
        l = row["l"] or 0
        n = w + l
        if n < _MIN_NONFLAT:
            break
        wr = w / n if n > 0 else 0

        if wr >= _TARGET_WR and n >= _MIN_NONFLAT:
            best_thresh = thresh
            best_wr = wr
            best_n = n
            best_w = w
            best_l = l
            found = True

        if wr < best_wr and found:
            break

    if not found:
        for step in range(0, 21):
            thresh = 0.80 + step * _SCAN_STEP
            row = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN outcome_200ticks='WIN' THEN 1 ELSE 0 END) as w,
                    SUM(CASE WHEN outcome_200ticks='LOSS' THEN 1 ELSE 0 END) as l
                FROM signal_log
                WHERE symbol=? AND direction=? AND score >= ?
                  AND outcome_200ticks IS NOT NULL
                  AND outcome_200ticks != 'FLAT'
                """,
                (symbol, direction, thresh),
            ).fetchone()
            w = row["w"] or 0
            l = row["l"] or 0
            n = w + l
            if n < _MIN_NONFLAT:
                break
            wr = w / n if n > 0 else 0
            if wr >= _MIN_WR and n >= _MIN_NONFLAT:
                if not found or wr > best_wr:
                    best_thresh = thresh
                    best_wr = wr
                    best_n = n
                    best_w = w
                    best_l = l
                    found = True
            if wr < _MIN_WR:
                break

    if not found:
        row = conn.execute(
            """
            SELECT
                SUM(CASE WHEN outcome_200ticks='WIN' THEN 1 ELSE 0 END) as w,
                SUM(CASE WHEN outcome_200ticks='LOSS' THEN 1 ELSE 0 END) as l
            FROM signal_log
            WHERE symbol=? AND direction=? AND score >= 0.80
              AND outcome_200ticks IS NOT NULL
              AND outcome_200ticks != 'FLAT'
            """,
            (symbol, direction),
        ).fetchone()
        w = row["w"] or 0
        l = row["l"] or 0
        n = w + l
        wr = w / n if n > 0 else 0
        best_thresh = 0.99 if wr < _MIN_WR else 0.80
        best_wr = wr
        best_n = n
        best_w = w
        best_l = l

    return {
        "symbol": symbol,
        "direction": direction,
        "threshold": round(best_thresh, 3),
        "wr": round(best_wr, 4),
        "wins": best_w,
        "losses": best_l,
        "nonflat": best_n,
        "tradable": best_wr >= _MIN_WR and best_n >= _MIN_NONFLAT,
    }


def get_dynamic_thresholds() -> Dict[str, dict]:
    global _cache, _cache_ts
    now = time.time()
    if _cache and (now - _cache_ts) < _CACHE_TTL:
        return _cache

    conn = _get_conn()
    if not conn:
        return _cache or {}

    result: Dict[str, dict] = {}
    try:
        pairs = conn.execute(
            """
            SELECT DISTINCT symbol, direction FROM signal_log
            WHERE outcome_200ticks IS NOT NULL
            """
        ).fetchall()

        for row in pairs:
            sym = row["symbol"]
            d = row["direction"]
            key = f"{sym}_{d}"
            info = _scan_threshold(conn, sym, d)
            if info:
                result[key] = info

        _cache = result
        _cache_ts = now

        tradable = [k for k, v in result.items() if v.get("tradable")]
        blocked = [k for k, v in result.items() if not v.get("tradable")]
        LOGGER.info(
            "Dynamic thresholds updated: %d tradable (%s), %d blocked (%s)",
            len(tradable),
            ", ".join(tradable[:6]),
            len(blocked),
            ", ".join(blocked[:6]),
        )
    except Exception as e:
        LOGGER.error("Dynamic threshold scan error: %s", e)
    finally:
        conn.close()

    return result


def get_threshold_for(symbol: str, direction: str) -> Tuple[float, bool]:
    thresholds = get_dynamic_thresholds()
    key = f"{symbol}_{direction}"
    info = thresholds.get(key, {})
    
    # BOOTSTRAP FALLBACK: If we have no data for this pair yet,
    # don't block it. Use a standard aggressive threshold.
    if not info:
        return 0.75, True
        
    return info.get("threshold", 0.99), info.get("tradable", False)


def get_summary() -> list:
    thresholds = get_dynamic_thresholds()
    out = []
    for key, info in sorted(thresholds.items()):
        out.append(info)
    return out
