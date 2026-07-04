import os
import logging
import sqlite3
import numpy as np
from collections import defaultdict

log = logging.getLogger(__name__)

_ENABLED = os.getenv("SEASONAL_PATTERNS_ENABLED", "true").lower() == "true"
_DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database", "overseer_trades.db"))
_MIN_SAMPLES = int(os.getenv("SEASONAL_MIN_SAMPLES", "10"))
_SMOOTHING_WINDOW = int(os.getenv("SEASONAL_SMOOTHING_WINDOW", "15"))


class SeasonalPatterns:
    def __init__(self):
        self._hourly_wr = {}
        self._dow_wr = {}
        self._loaded = False

    def load_from_db(self, db_path=None):
        if not _ENABLED:
            return
        dp = db_path or _DB_PATH
        try:
            conn = sqlite3.connect(dp, timeout=10)
            cur = conn.cursor()
            cur.execute("""
                SELECT symbol, direction,
                       CAST(strftime('%H', timestamp) AS INTEGER) as hour,
                       CAST(strftime('%w', timestamp) AS INTEGER) as dow,
                       CASE WHEN outcome_200ticks = 'WIN' THEN 1 ELSE 0 END as won
                FROM signal_log
                WHERE outcome_200ticks IS NOT NULL AND outcome_200ticks != 'FLAT'
            """)
            rows = cur.fetchall()
            conn.close()
            hour_data = defaultdict(lambda: {"wins": 0, "total": 0})
            dow_data = defaultdict(lambda: {"wins": 0, "total": 0})
            for symbol, direction, hour, dow, won in rows:
                hkey = (symbol, direction, hour)
                hour_data[hkey]["wins"] += won
                hour_data[hkey]["total"] += 1
                dkey = (symbol, direction, dow)
                dow_data[dkey]["wins"] += won
                dow_data[dkey]["total"] += 1
            for key, d in hour_data.items():
                if d["total"] >= _MIN_SAMPLES:
                    self._hourly_wr[key] = d["wins"] / d["total"]
            for key, d in dow_data.items():
                if d["total"] >= _MIN_SAMPLES:
                    self._dow_wr[key] = d["wins"] / d["total"]
            self._loaded = True
            log.info(f"SeasonalPatterns loaded: {len(self._hourly_wr)} hourly, {len(self._dow_wr)} DOW entries")
        except Exception as e:
            log.warning(f"SeasonalPatterns load failed: {e}")

    def get_hourly_multiplier(self, symbol, direction, hour=None):
        if not _ENABLED or not self._loaded:
            return 1.0
        if hour is None:
            hour = datetime.now(timezone.utc).hour
        key = (symbol, direction, hour)
        wr = self._hourly_wr.get(key)
        if wr is None:
            return 1.0
        overall = 0.55
        return wr / overall if overall > 0 else 1.0

    def get_dow_multiplier(self, symbol, direction, dow=None):
        if not _ENABLED or not self._loaded:
            return 1.0
        if dow is None:
            dow = datetime.now(timezone.utc).weekday()
            dow = (dow + 1) % 7
        key = (symbol, direction, dow)
        wr = self._dow_wr.get(key)
        if wr is None:
            return 1.0
        overall = 0.55
        return wr / overall if overall > 0 else 1.0


seasonal_patterns = SeasonalPatterns()
