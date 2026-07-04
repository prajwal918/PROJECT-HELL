from __future__ import annotations

import os
from collections import deque
from typing import Any

import numpy as np

from .base_gate import BaseGate

_BB_PERIOD = int(os.getenv("GATE_BB_PERIOD", "20"))
_BB_STD_MULT = float(os.getenv("GATE_BB_STD_MULT", "2.0"))
_BB_WINDOW = int(os.getenv("GATE_BB_WINDOW", "100"))


class GateBB(BaseGate):
    gate_name = "gate_BB"
    priority = 32

    def __init__(self) -> None:
        self._mids: deque[float] = deque(maxlen=_BB_WINDOW)

    def evaluate(self, tick: dict[str, Any]) -> bool:
        bid = float(tick.get("bid", 0.0))
        ask = float(tick.get("ask", 0.0))
        if bid <= 0 or ask <= 0:
            return True
        mid = (bid + ask) / 2.0
        self._mids.append(mid)
        if len(self._mids) < _BB_PERIOD:
            return True
        prices = np.array(list(self._mids)[-_BB_PERIOD:])
        sma = float(np.mean(prices))
        std = float(np.std(prices))
        upper = sma + _BB_STD_MULT * std
        lower = sma - _BB_STD_MULT * std
        bandwidth = upper - lower
        tick["bb_upper"] = upper
        tick["bb_lower"] = lower
        tick["bb_sma"] = sma
        tick["bb_pct"] = (mid - lower) / bandwidth if bandwidth > 0 else 0.5
        direction = tick.get("direction", "BUY")
        if direction == "BUY":
            if mid < lower:
                return False
            pct = tick["bb_pct"]
            if pct < 0.2:
                return False
        if direction == "SELL":
            if mid > upper:
                return False
            pct = tick["bb_pct"]
            if pct > 0.8:
                return False
        return True
