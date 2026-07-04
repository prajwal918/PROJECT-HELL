import os
import logging

log = logging.getLogger(__name__)

_ENABLED = os.getenv("SWAP_ANOMALY_ENABLED", "true").lower() == "true"
_SWAP_DEVIATION_THRESHOLD = float(os.getenv("SWAP_DEVIATION_THRESHOLD", "0.5"))
_SWAP_ANOMALY_BONUS = float(os.getenv("SWAP_ANOMALY_BONUS", "0.05"))


class SwapAnomaly:
    def __init__(self):
        self._theoretical_swap = {}
        self._actual_swap = {}
        self._anomalies = {}

    def set_rates(self, symbol, domestic_rate, foreign_rate):
        self._theoretical_swap[symbol] = (domestic_rate - foreign_rate) / 365.0

    def update_actual_swap(self, symbol, swap_points):
        self._actual_swap[symbol] = swap_points

    def detect_anomaly(self, symbol):
        if not _ENABLED:
            return False, 0.0, None
        theoretical = self._theoretical_swap.get(symbol)
        actual = self._actual_swap.get(symbol)
        if theoretical is None or actual is None:
            return False, 0.0, None
        deviation = actual - theoretical
        if abs(deviation) > _SWAP_DEVIATION_THRESHOLD:
            direction = "BUY" if deviation > 0 else "SELL"
            self._anomalies[symbol] = {"deviation": deviation, "direction": direction}
            return True, deviation, direction
        return False, 0.0, None

    def get_bonus(self, symbol, trade_direction):
        if not _ENABLED:
            return 0.0
        anomaly = self._anomalies.get(symbol)
        if anomaly and anomaly["direction"] == trade_direction:
            return _SWAP_ANOMALY_BONUS
        return 0.0


swap_anomaly = SwapAnomaly()
