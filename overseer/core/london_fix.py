import os
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

_ENABLED = os.getenv("LONDON_FIX_ENABLED", "true").lower() == "true"
_FIX_BONUS = float(os.getenv("LONDON_FIX_BONUS", "0.08"))
_FIX_START_HOUR = int(os.getenv("LONDON_FIX_START_HOUR", "15"))
_FIX_START_MIN = int(os.getenv("LONDON_FIX_START_MIN", "45"))
_FIX_END_HOUR = int(os.getenv("LONDON_FIX_END_HOUR", "16"))
_FIX_END_MIN = int(os.getenv("LONDON_FIX_END_MIN", "10"))


class LondonFix:
    def __init__(self):
        self._day_trend = {}
        self._session_direction = {}

    def update_session_trend(self, symbol, direction):
        self._session_direction[symbol] = direction

    def is_fix_window(self, now_utc=None):
        if not _ENABLED:
            return False
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)
        h, m = now_utc.hour, now_utc.minute
        if h == _FIX_START_HOUR and m >= _FIX_START_MIN:
            return True
        if h == _FIX_END_HOUR and m <= _FIX_END_MIN:
            return True
        return False

    def get_bonus(self, symbol, trade_direction):
        if not _ENABLED:
            return 0.0
        if not self.is_fix_window():
            return 0.0
        session_dir = self._session_direction.get(symbol)
        if session_dir is None:
            return 0.0
        if session_dir == trade_direction:
            return _FIX_BONUS
        return 0.0


london_fix = LondonFix()
