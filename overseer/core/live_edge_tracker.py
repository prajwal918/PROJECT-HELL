import os
import logging
import sqlite3
from collections import defaultdict, deque

log = logging.getLogger(__name__)

_ENABLED = os.getenv("LIVE_EDGE_TRACKER_ENABLED", "true").lower() == "true"
_DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database", "overseer_trades.db"))
_WINDOW = int(os.getenv("LIVE_EDGE_WINDOW", "20"))
_SKIP_BELOW = float(os.getenv("LIVE_EDGE_SKIP_BELOW", "0.50"))
_SIZE_UP_ABOVE = float(os.getenv("LIVE_EDGE_SIZE_UP_ABOVE", "0.70"))


class LiveEdgeTracker:
    def __init__(self):
        self._outcomes = defaultdict(lambda: deque(maxlen=_WINDOW))
        self._rolling_wr = {}

    def record_outcome(self, symbol, direction, won):
        if not _ENABLED:
            return
        key = f"{symbol}_{direction}"
        self._outcomes[key].append(1.0 if won else 0.0)
        outcomes = self._outcomes[key]
        if len(outcomes) >= 5:
            self._rolling_wr[key] = sum(outcomes) / len(outcomes)

    def get_wr(self, symbol, direction):
        key = f"{symbol}_{direction}"
        return self._rolling_wr.get(key, 0.55)

    def should_skip(self, symbol, direction):
        if not _ENABLED:
            return False
        wr = self.get_wr(symbol, direction)
        if len(self._outcomes[f"{symbol}_{direction}"]) < 5:
            return False
        return wr < _SKIP_BELOW

    def get_size_multiplier(self, symbol, direction):
        if not _ENABLED:
            return 1.0
        wr = self.get_wr(symbol, direction)
        key = f"{symbol}_{direction}"
        if len(self._outcomes[key]) < 5:
            return 1.0
        if wr > _SIZE_UP_ABOVE:
            return min(1.0 + (wr - _SIZE_UP_ABOVE) * 2.0, 1.25)
        elif wr < _SKIP_BELOW:
            return max(1.0 - (_SKIP_BELOW - wr) * 2.0, 0.50)
        return 1.0

    def backfill_from_db(self, db_path=None):
        dp = db_path or _DB_PATH
        try:
            conn = sqlite3.connect(dp, timeout=10)
            cur = conn.cursor()
            cur.execute("""
                SELECT symbol, direction, outcome_200ticks
                FROM signal_log
                WHERE outcome_200ticks IS NOT NULL AND outcome_200ticks != 'FLAT'
                ORDER BY id DESC LIMIT 5000
            """)
            rows = cur.fetchall()
            conn.close()
            for symbol, direction, outcome in reversed(rows):
                won = outcome == "WIN"
                key = f"{symbol}_{direction}"
                self._outcomes[key].append(1.0 if won else 0.0)
            for key in self._outcomes:
                outcomes = self._outcomes[key]
                if len(outcomes) >= 5:
                    self._rolling_wr[key] = sum(outcomes) / len(outcomes)
            log.info(f"LiveEdgeTracker backfilled {sum(len(v) for v in self._outcomes.values())} outcomes")
        except Exception as e:
            log.warning(f"LiveEdgeTracker backfill failed: {e}")


live_edge_tracker = LiveEdgeTracker()
