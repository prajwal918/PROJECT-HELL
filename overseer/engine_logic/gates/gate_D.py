from __future__ import annotations

import os
from collections import deque
from typing import Any

from .base_gate import BaseGate

MOMENTUM_LOOKBACK = int(os.getenv("GATE_D_LOOKBACK", "4"))


class GateD(BaseGate):
    gate_name = "gate_D"
    priority = 4

    def __init__(self) -> None:
        self._mids: deque[float] = deque(maxlen=MOMENTUM_LOOKBACK + 1)

    def evaluate(self, tick: dict[str, Any]) -> bool:
        bid = float(tick.get("bid", 0.0))
        ask = float(tick.get("ask", 0.0))
        if bid <= 0 or ask <= 0 or ask <= bid:
            return False
        mid = (bid + ask) / 2.0
        self._mids.append(mid)
        if len(self._mids) < 2:
            return True
        pip_size = float(tick.get("pip_size", 0.0001))
        velocity_threshold = float(tick.get("velocity_threshold", 0.0003))
        direction = tick.get("direction", "")
        lookback = min(MOMENTUM_LOOKBACK, len(self._mids) - 1)
        momentum = mid - self._mids[-(lookback + 1)]
        if direction == "BUY":
            return momentum > velocity_threshold
        elif direction == "SELL":
            return momentum < -velocity_threshold
        return abs(momentum) > velocity_threshold
