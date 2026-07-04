import os
import logging
from collections import deque
from datetime import datetime, timezone

log = logging.getLogger(__name__)

_ENABLED = os.getenv("SIGNAL_FREQUENCY_ENABLED", "true").lower() == "true"
_NOISY_THRESHOLD = float(os.getenv("SIGNAL_FREQUENCY_NOISY_THRESHOLD", "8.0"))
_CLEAN_THRESHOLD = float(os.getenv("SIGNAL_FREQUENCY_CLEAN_THRESHOLD", "2.0"))
_NOISY_MULT = float(os.getenv("SIGNAL_FREQUENCY_NOISY_MULT", "0.85"))
_CLEAN_MULT = float(os.getenv("SIGNAL_FREQUENCY_CLEAN_MULT", "1.10"))
_WINDOW_SECONDS = int(os.getenv("SIGNAL_FREQUENCY_WINDOW_SECONDS", "3600"))


class SignalFrequency:
    def __init__(self):
        self._signal_times = deque(maxlen=500)

    def record_signal(self):
        if not _ENABLED:
            return
        self._signal_times.append(datetime.now(timezone.utc).timestamp())

    def get_multiplier(self):
        if not _ENABLED:
            return 1.0
        now = datetime.now(timezone.utc).timestamp()
        cutoff = now - _WINDOW_SECONDS
        count = sum(1 for t in self._signal_times if t > cutoff)
        if count > _NOISY_THRESHOLD:
            return _NOISY_MULT
        elif count <= _CLEAN_THRESHOLD:
            return _CLEAN_MULT
        return 1.0

    def get_signal_count_last_hour(self):
        now = datetime.now(timezone.utc).timestamp()
        cutoff = now - _WINDOW_SECONDS
        return sum(1 for t in self._signal_times if t > cutoff)


signal_frequency = SignalFrequency()
