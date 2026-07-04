from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "overseer_trades.db"

LOGGER = logging.getLogger("overseer.cot_crowding")

_CROWDING_ZSCORE_THRESHOLD = float(__import__("os").getenv("COT_CROWDING_ZSCORE", "2.0"))
_CACHE_TTL_SECONDS = float(__import__("os").getenv("COT_CROWDING_CACHE_TTL", "3600"))

_cache = {"data": None, "ts": 0.0}


def _load_cot_data() -> dict[str, dict[str, float]]:
    import time
    now = time.monotonic()
    if _cache["data"] is not None and (now - _cache["ts"]) < _CACHE_TTL_SECONDS:
        return _cache["data"]

    result = {}
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        rows = conn.execute(
            "SELECT symbol, net_position, timestamp FROM cot_positions ORDER BY timestamp DESC"
        ).fetchall()
        conn.close()

        by_symbol = {}
        for sym, net_pos, ts in rows:
            if sym not in by_symbol:
                by_symbol[sym] = []
            by_symbol[sym].append(float(net_pos))

        for sym, positions in by_symbol.items():
            if len(positions) < 10:
                continue
            current = positions[0]
            hist = positions[1:]
            if not hist:
                continue
            mean = sum(hist) / len(hist)
            std = (sum((x - mean) ** 2 for x in hist) / len(hist)) ** 0.5
            if std > 0:
                zscore = (current - mean) / std
            else:
                zscore = 0.0
            result[sym] = {
                "current": current,
                "mean": mean,
                "std": std,
                "zscore": zscore,
                "is_crowded": abs(zscore) > _CROWDING_ZSCORE_THRESHOLD,
            }
    except Exception as e:
        LOGGER.debug("COT crowding load error: %s", e)

    _cache["data"] = result
    _cache["ts"] = now
    return result


def get_crowding_signal(symbol: str) -> dict[str, Any]:
    data = _load_cot_data()
    sym_key = symbol[:2] if len(symbol) >= 2 else symbol
    info = data.get(sym_key, data.get(symbol, {}))
    if not info:
        return {"is_crowded": False, "zscore": 0.0, "direction": None}

    direction = None
    if info["is_crowded"]:
        direction = "SELL" if info["zscore"] > 0 else "BUY"

    return {
        "is_crowded": info["is_crowded"],
        "zscore": info.get("zscore", 0.0),
        "direction": direction,
        "current_position": info.get("current", 0.0),
    }


def get_crowding_bonus(symbol: str, trade_direction: str) -> float:
    signal = get_crowding_signal(symbol)
    if not signal["is_crowded"]:
        return 0.0
    crowding_dir = signal.get("direction")
    if crowding_dir == trade_direction:
        return -0.05
    if crowding_dir is not None and crowding_dir != trade_direction:
        return 0.03
    return 0.0
