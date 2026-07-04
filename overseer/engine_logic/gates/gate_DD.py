from __future__ import annotations

import os
from collections import deque
from typing import Any

import numpy as np

from .base_gate import BaseGate

_DD_WINDOW = int(os.getenv("GATE_DD_WINDOW", "50"))
_DD_DIVERGENCE_THRESHOLD = float(os.getenv("GATE_DD_DIVERGENCE_THRESHOLD", "0.3"))


class GateDD(BaseGate):
    gate_name = "gate_DD"
    priority = 27

    def __init__(self) -> None:
        self._mids: deque[float] = deque(maxlen=_DD_WINDOW)
        self._deltas: deque[float] = deque(maxlen=_DD_WINDOW)

    def evaluate(self, tick: dict[str, Any]) -> bool:
        bid = float(tick.get("bid", 0.0))
        ask = float(tick.get("ask", 0.0))
        delta = float(tick.get("delta", 0.0))
        if bid <= 0 or ask <= 0:
            return True
        mid = (bid + ask) / 2.0
        self._mids.append(mid)
        self._deltas.append(delta)
        if len(self._mids) < 20:
            return True
        mids = np.array(self._mids)
        deltas = np.array(self._deltas)
        n = len(mids)
        half = n // 2
        price_change = mids[-1] - mids[half]
        delta_sum_second = float(np.sum(deltas[half:]))
        pip_size = float(tick.get("pip_size", 0.0001))
        if pip_size <= 0:
            pip_size = 0.0001
        price_pips = price_change / pip_size
        if abs(price_pips) < 0.5:
            return True
        direction = tick.get("direction", "BUY")
        if direction == "BUY":
            price_going_up = price_pips > 0
            delta_bullish = delta_sum_second > 0
            if price_going_up and not delta_bullish:
                bearish_div = abs(delta_sum_second) / max(abs(price_pips), 1.0)
                return bearish_div < _DD_DIVERGENCE_THRESHOLD
        if direction == "SELL":
            price_going_down = price_pips < 0
            delta_bearish = delta_sum_second < 0
            if price_going_down and not delta_bearish:
                bullish_div = abs(delta_sum_second) / max(abs(price_pips), 1.0)
                return bullish_div < _DD_DIVERGENCE_THRESHOLD
        return True
