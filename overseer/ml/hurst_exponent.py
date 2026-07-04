import os
import logging
import numpy as np
from collections import deque

log = logging.getLogger(__name__)

_ENABLED = os.getenv("HURST_EXPONENT_ENABLED", "true").lower() == "true"
_WINDOW = int(os.getenv("HURST_WINDOW_SIZE", "100"))
_MOMENTUM_THRESHOLD = float(os.getenv("HURST_MOMENTUM_THRESHOLD", "0.60"))
_REVERSAL_THRESHOLD = float(os.getenv("HURST_REVERSAL_THRESHOLD", "0.40"))
_MOMENTUM_BONUS = float(os.getenv("HURST_MOMENTUM_BONUS", "0.04"))
_REVERSAL_BONUS = float(os.getenv("HURST_REVERSAL_BONUS", "0.04"))


def _compute_hurst(series):
    if len(series) < 20:
        return 0.5
    try:
        lags = range(2, min(len(series) // 2, 50))
        if len(list(lags)) < 5:
            return 0.5
        tau = []
        valid_lags = []
        for lag in lags:
            if lag >= len(series):
                continue
            diff = series[lag:] - series[:-lag]
            if len(diff) == 0:
                continue
            std = np.std(diff)
            if std > 0:
                tau.append(np.log(std))
                valid_lags.append(np.log(lag))
        if len(tau) < 5:
            return 0.5
        reg = np.polyfit(valid_lags, tau, 1)
        return float(reg[0])
    except Exception:
        return 0.5


class HurstExponent:
    def __init__(self):
        self._prices = {}
        self._hurst = {}

    def on_tick(self, symbol, mid):
        if symbol not in self._prices:
            self._prices[symbol] = deque(maxlen=_WINDOW * 2)
        self._prices[symbol].append(mid)

    def compute(self, symbol):
        if not _ENABLED:
            return 0.5
        prices = self._prices.get(symbol, deque())
        if len(prices) < _WINDOW:
            self._hurst[symbol] = 0.5
            return 0.5
        arr = np.array(list(prices)[-_WINDOW:])
        returns = np.diff(np.log(arr[arr > 0])) if arr.min() > 0 else np.diff(arr)
        h = _compute_hurst(returns)
        self._hurst[symbol] = h
        return h

    def get_gating_bonus(self, symbol, trade_direction, gate_type):
        if not _ENABLED:
            return 0.0
        h = self._hurst.get(symbol, 0.5)
        if gate_type == "momentum" and h > _MOMENTUM_THRESHOLD:
            return _MOMENTUM_BONUS * (h - 0.5) / 0.5
        elif gate_type == "reversal" and h < _REVERSAL_THRESHOLD:
            return _REVERSAL_BONUS * (0.5 - h) / 0.5
        return 0.0

    def get_behavior(self, symbol):
        h = self._hurst.get(symbol, 0.5)
        if h > _MOMENTUM_THRESHOLD:
            return "TRENDING"
        elif h < _REVERSAL_THRESHOLD:
            return "MEAN_REVERTING"
        return "RANDOM"


hurst_exponent = HurstExponent()
