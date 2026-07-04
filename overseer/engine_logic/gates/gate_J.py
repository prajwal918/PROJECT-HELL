from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

JUMP_PIPS_THRESHOLD = float(os.getenv("GATE_J_JUMP_PIPS", "3.0"))


class GateJ(BaseGate):
    gate_name = "gate_J"
    priority = 10

    def __init__(self) -> None:
        self._prev_mid: float = 0.0

    def evaluate(self, tick: dict[str, Any]) -> bool:
        bid = float(tick.get("bid", 0.0))
        ask = float(tick.get("ask", 0.0))
        if bid <= 0 or ask <= 0:
            return False
        mid = (bid + ask) / 2.0
        if self._prev_mid <= 0:
            self._prev_mid = mid
            return True
        pip_size = 0.01 if "JPY" in str(tick.get("symbol", "")) else 0.0001
        jump_pips = abs(mid - self._prev_mid) / pip_size
        self._prev_mid = mid
        return jump_pips <= JUMP_PIPS_THRESHOLD
