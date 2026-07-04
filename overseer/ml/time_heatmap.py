import os
import logging
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

log = logging.getLogger(__name__)

_ENABLED = os.getenv("TIME_HEATMAP_ENABLED", "true").lower() == "true"
_DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database", "overseer_trades.db"))
_MIN_SAMPLE = int(os.getenv("TIME_HEATMAP_MIN_SAMPLE", "5"))
_BLOCK_BELOW = float(os.getenv("TIME_HEATMAP_BLOCK_BELOW", "0.45"))
_BOOST_ABOVE = float(os.getenv("TIME_HEATMAP_BOOST_ABOVE", "0.70"))
_REFRESH_INTERVAL = int(os.getenv("TIME_HEATMAP_REFRESH_SECONDS", "300"))


class TimeHeatmap:
    def __init__(self):
        self._heatmap = {}
        self._last_refresh = 0

    def refresh(self, db_path=None):
        dp = db_path or _DB_PATH
        try:
            conn = sqlite3.connect(dp, timeout=10)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT symbol, direction, CAST(strftime('%H', timestamp) AS INTEGER) as hour,
                       COUNT(*) as total,
                       SUM(CASE WHEN outcome_200ticks = 'WIN' THEN 1 ELSE 0 END) as wins
                FROM signal_log
                WHERE outcome_200ticks IS NOT NULL
                GROUP BY symbol, direction, hour
            """)
            rows = cur.fetchall()
            conn.close()
            self._heatmap.clear()
            for r in rows:
                key = (r["symbol"], r["direction"], r["hour"])
                wr = r["wins"] / r["total"] if r["total"] > 0 else 0.5
                self._heatmap[key] = {"wr": wr, "n": r["total"]}
        except Exception as e:
            log.warning(f"TimeHeatmap refresh failed: {e}")

    def get_multiplier(self, symbol, direction, hour=None):
        if not _ENABLED:
            return 1.0
        if hour is None:
            hour = datetime.now(timezone.utc).hour
        key = (symbol, direction, hour)
        entry = self._heatmap.get(key)
        if entry is None or entry["n"] < _MIN_SAMPLE:
            return 1.0
        wr = entry["wr"]
        if wr < _BLOCK_BELOW:
            return 0.70
        elif wr > _BOOST_ABOVE:
            return 1.10
        return 1.0

    def should_block(self, symbol, direction, hour=None):
        if not _ENABLED:
            return False
        if hour is None:
            hour = datetime.now(timezone.utc).hour
        key = (symbol, direction, hour)
        entry = self._heatmap.get(key)
        if entry is None or entry["n"] < _MIN_SAMPLE:
            return False
        return entry["wr"] < _BLOCK_BELOW


time_heatmap = TimeHeatmap()
