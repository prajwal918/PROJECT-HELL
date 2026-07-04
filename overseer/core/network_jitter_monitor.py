import os
import logging
from collections import deque

log = logging.getLogger(__name__)

_ENABLED = os.getenv("NETWORK_JITTER_MONITOR_ENABLED", "true").lower() == "true"
_DEGRADED_THRESHOLD_MS = float(os.getenv("NETWORK_JITTER_DEGRADED_MS", "5.0"))
_EXCELLENT_THRESHOLD_MS = float(os.getenv("NETWORK_JITTER_EXCELLENT_MS", "1.0"))


class NetworkJitterMonitor:
    def __init__(self):
        self._intervals = {}
        self._last_tick_time = {}
        self._quality = {}

    def on_tick(self, symbol, timestamp_ns):
        if symbol not in self._intervals:
            self._intervals[symbol] = deque(maxlen=20)
            self._last_tick_time[symbol] = 0
        if self._last_tick_time[symbol] > 0:
            interval = timestamp_ns - self._last_tick_time[symbol]
            if interval > 0:
                self._intervals[symbol].append(interval)
        self._last_tick_time[symbol] = timestamp_ns

    def get_jitter_ms(self, symbol):
        intervals = self._intervals.get(symbol, deque())
        if len(intervals) < 5:
            return 0.0
        import statistics
        try:
            jitter_ns = statistics.stdev(intervals)
            return jitter_ns / 1e6
        except Exception:
            return 0.0

    def get_quality(self, symbol):
        if not _ENABLED:
            return "EXCELLENT"
        jitter = self.get_jitter_ms(symbol)
        if jitter > _DEGRADED_THRESHOLD_MS:
            quality = "DEGRADED"
        elif jitter < _EXCELLENT_THRESHOLD_MS:
            quality = "EXCELLENT"
        else:
            quality = "NORMAL"
        self._quality[symbol] = quality
        return quality


network_jitter_monitor = NetworkJitterMonitor()
