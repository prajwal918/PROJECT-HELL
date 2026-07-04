import os
import logging
from collections import deque

log = logging.getLogger(__name__)

_ENABLED = os.getenv("HAWKES_PROCESS_ENABLED", "true").lower() == "true"
_BURST_PREDICTION_THRESHOLD = float(os.getenv("HAWKES_BURST_THRESHOLD", "2.0"))


class HawkesProcess:
    def __init__(self):
        self._tick_times = {}
        self._alpha = 0.8
        self._beta = 1.2
        self._mu = 0.1
        self._last_intensity = {}

    def on_tick(self, symbol, timestamp):
        if symbol not in self._tick_times:
            self._tick_times[symbol] = deque(maxlen=1000)
        self._tick_times[symbol].append(timestamp)

    def compute_intensity(self, symbol, current_time):
        times = self._tick_times.get(symbol, deque())
        if len(times) < 10:
            return self._mu
        intensity = self._mu
        for t in times:
            dt = current_time - t
            if dt > 0:
                intensity += self._alpha * _beta * float(os.getenv("HAWKES_DECAY", str(self._beta))) * (-self._beta * dt)
        return max(intensity, self._mu)

    def predict_burst(self, symbol, current_time, horizon_seconds=10):
        if not _ENABLED:
            return 1.0, False
        current_intensity = self.compute_intensity(symbol, current_time)
        self._last_intensity[symbol] = current_intensity
        predicted = current_intensity * 1.5
        burst = predicted > current_intensity * _BURST_PREDICTION_THRESHOLD
        return predicted, burst

    def get_entry_urgency(self, symbol, current_time):
        if not _ENABLED:
            return "NORMAL"
        predicted, burst = self.predict_burst(symbol, current_time)
        if burst:
            return "NOW"
        current = self._last_intensity.get(symbol, self._mu)
        if current < self._mu * 0.3:
            return "WAIT"
        return "NORMAL"


hawkes_process = HawkesProcess()
