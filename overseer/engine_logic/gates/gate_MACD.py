from __future__ import annotations

import os
from collections import deque
from typing import Any

import numpy as np

from .base_gate import BaseGate

_MACD_FAST = int(os.getenv("GATE_MACD_FAST", "12"))
_MACD_SLOW = int(os.getenv("GATE_MACD_SLOW", "26"))
_MACD_SIGNAL = int(os.getenv("GATE_MACD_SIGNAL", "9"))
_MACD_WINDOW = int(os.getenv("GATE_MACD_WINDOW", "100"))


class GateMACD(BaseGate):
    gate_name = "gate_MACD"
    priority = 31

    def __init__(self) -> None:
        self._mids: deque[float] = deque(maxlen=_MACD_WINDOW)
        self._ema_fast: float | None = None
        self._ema_slow: float | None = None
        self._signal_line: deque[float] = deque(maxlen=_MACD_SIGNAL)
        self._prev_histogram: float | None = None

    def evaluate(self, tick: dict[str, Any]) -> bool:
        bid = float(tick.get("bid", 0.0))
        ask = float(tick.get("ask", 0.0))
        if bid <= 0 or ask <= 0:
            return True
        mid = (bid + ask) / 2.0
        self._mids.append(mid)
        if len(self._mids) < _MACD_SLOW:
            return True
        alpha_fast = 2.0 / (_MACD_FAST + 1.0)
        alpha_slow = 2.0 / (_MACD_SLOW + 1.0)
        if self._ema_fast is None:
            prices = list(self._mids)
            self._ema_fast = float(np.mean(prices[:_MACD_FAST]))
            self._ema_slow = float(np.mean(prices[:_MACD_SLOW]))
        self._ema_fast = (mid - self._ema_fast) * alpha_fast + self._ema_fast
        self._ema_slow = (mid - self._ema_slow) * alpha_slow + self._ema_slow
        macd_line = self._ema_fast - self._ema_slow
        self._signal_line.append(macd_line)
        if len(self._signal_line) < _MACD_SIGNAL:
            return True
        signal = float(np.mean(list(self._signal_line)))
        histogram = macd_line - signal
        tick["macd_line"] = macd_line
        tick["macd_signal"] = signal
        tick["macd_histogram"] = histogram
        direction = tick.get("direction", "BUY")
        if self._prev_histogram is not None:
            if direction == "BUY":
                if self._prev_histogram <= 0 and histogram > 0:
                    return True
                if histogram < 0:
                    return False
            if direction == "SELL":
                if self._prev_histogram >= 0 and histogram < 0:
                    return True
                if histogram > 0:
                    return False
        self._prev_histogram = histogram
        return True
