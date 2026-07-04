from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

MAX_SPREAD_BPS = float(os.getenv("GATE_S_MAX_SPREAD_BPS", "6.0"))
SPREAD_WIDENING_MULT = float(os.getenv("GATE_S_SPREAD_WIDENING_MULT", "2.0"))


class GateS(BaseGate):
    gate_name = "gate_S"
    priority = 19

    def __init__(self) -> None:
        self._avg_spread: float = 0.0
        self._spread_count: int = 0

    def evaluate(self, tick: dict[str, Any]) -> bool:
        spread_bps = float(tick.get("spread_bps", 0.0))
        if spread_bps <= 0:
            return True
        if spread_bps > MAX_SPREAD_BPS:
            return False
        self._spread_count += 1
        alpha = 1.0 / min(self._spread_count, 200)
        self._avg_spread = self._avg_spread * (1.0 - alpha) + spread_bps * alpha
        if self._avg_spread > 0 and spread_bps > self._avg_spread * SPREAD_WIDENING_MULT:
            return False
        return True
