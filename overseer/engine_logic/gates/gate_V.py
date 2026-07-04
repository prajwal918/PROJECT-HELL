from __future__ import annotations

import os
from collections import deque
from typing import Any

import numpy as np

from .base_gate import BaseGate

VOLATILITY_WINDOW = int(os.getenv("GATE_V_WINDOW", "50"))


class GateV(BaseGate):
    gate_name = "gate_V"
    priority = 22

    def __init__(self) -> None:
        self._mid_buffer: deque[float] = deque(maxlen=VOLATILITY_WINDOW)

    def evaluate(self, tick: dict[str, Any]) -> bool:
        bid = float(tick.get("bid", 0.0))
        ask = float(tick.get("ask", 0.0))
        if bid <= 0 or ask <= 0:
            return False
        mid = (bid + ask) / 2.0
        self._mid_buffer.append(mid)
        if len(self._mid_buffer) < 10:
            return True
        prices = np.array(self._mid_buffer)
        returns = np.diff(prices) / prices[:-1]
        atr_bps = float(np.std(returns) * 10000.0) if len(returns) >= 2 else 0.0
        min_atr = float(tick.get("atr_bps_min", MIN_ATR_BPS))
        max_atr = float(tick.get("atr_bps_max", MAX_ATR_BPS))
        if atr_bps < min_atr:
            return False
        if atr_bps > max_atr:
            return False
        return True
