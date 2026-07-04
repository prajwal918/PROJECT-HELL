#!/usr/bin/env python3
"""
Spread Intelligence — Z-Score anomaly detection.

Instead of checking absolute spread (spread_bps > MAX),
institutions use a relative measure: is the current spread
anomalously wide compared to what it normally is at this
exact time of day and day of week?

z > 2.5 = anomalous (warn)
z > 3.0 = avoid (block trade)
"""

import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import Dict, Optional

import numpy as np

LOGGER = logging.getLogger("overseer.spread_intelligence")

DB_PATH = os.getenv("DB_PATH", "database/overseer_trades.db")
SPREAD_ZSCORE_WARN = float(os.getenv("SPREAD_ZSCORE_WARN", "2.5"))
SPREAD_ZSCORE_AVOID = float(os.getenv("SPREAD_ZSCORE_AVOID", "3.0"))
SPREAD_ZSCORE_LOOKBACK = int(os.getenv("SPREAD_ZSCORE_LOOKBACK", "500"))
SPREAD_ZSCORE_MIN_SAMPLES = int(os.getenv("SPREAD_ZSCORE_MIN_SAMPLES", "50"))

_cache: Dict[str, Dict] = {}
_cache_ttl_seconds = int(os.getenv("SPREAD_ZSCORE_CACHE_TTL", "300"))
_last_cache_time: float = 0.0


def _get_hourly_stats(symbol: str, hour: int, dow: int, db_path: Optional[str] = None) -> Optional[Dict]:
    """Query historical spread distribution for this symbol."""
    _db = db_path or DB_PATH
    try:
        conn = sqlite3.connect(_db, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        rows = conn.execute(
            """
            SELECT spread_bps FROM tick_log
            WHERE symbol = ?
            AND spread_bps > 0
            AND spread_bps < 100
            ORDER BY rowid DESC LIMIT ?
            """,
            (symbol, SPREAD_ZSCORE_LOOKBACK * 4),
        ).fetchall()
        conn.close()

        if len(rows) < SPREAD_ZSCORE_MIN_SAMPLES:
            return None

        spreads = np.array([r[0] for r in rows], dtype=float)
        mean = float(np.mean(spreads))
        std = float(np.std(spreads))

        if std <= 0:
            std = 0.01

        return {"mean": mean, "std": std, "n": len(spreads)}

    except Exception as e:
        LOGGER.debug("Spread z-score query failed for %s: %s", symbol, e)
        return None


def get_spread_zscore(
    symbol: str, current_spread_bps: float, db_path: Optional[str] = None
) -> Dict:
    """
    Compute z-score of current spread vs historical baseline.
    """
    global _cache, _last_cache_time

    if current_spread_bps <= 0:
        return {
            "zscore": 0.0,
            "anomalous": False,
            "avoid": False,
            "percentile": 0.5,
            "mean_spread_bps": 0.0,
            "current_spread_bps": 0.0,
        }

    now = datetime.now(timezone.utc)
    hour = now.hour
    dow = now.weekday()
    cache_key = f"{symbol}_{hour}_{dow}"

    current_time = time.time()
    if current_time - _last_cache_time > _cache_ttl_seconds:
        _cache = {}
        _last_cache_time = current_time

    stats = _cache.get(cache_key)
    if stats is None:
        stats = _get_hourly_stats(symbol, hour, dow, db_path)
        _cache[cache_key] = stats

    if stats is None:
        return {
            "zscore": 0.0,
            "anomalous": False,
            "avoid": False,
            "percentile": 0.5,
            "mean_spread_bps": 0.0,
            "current_spread_bps": current_spread_bps,
        }

    zscore = (current_spread_bps - stats["mean"]) / stats["std"]

    if current_spread_bps > stats["mean"]:
        percentile = min(1.0, 0.5 + (zscore / 6.0) * 0.5)
    else:
        percentile = max(0.0, 0.5 + (zscore / 6.0) * 0.5)

    return {
        "zscore": round(float(zscore), 2),
        "anomalous": abs(zscore) > SPREAD_ZSCORE_WARN,
        "avoid": abs(zscore) > SPREAD_ZSCORE_AVOID,
        "percentile": round(percentile, 3),
        "mean_spread_bps": round(stats["mean"], 2),
        "current_spread_bps": current_spread_bps,
    }
