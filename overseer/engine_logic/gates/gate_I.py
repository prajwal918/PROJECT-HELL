from __future__ import annotations

from typing import Any

from .base_gate import BaseGate


class GateI(BaseGate):
    gate_name = "gate_I"
    priority = 9

    def evaluate(self, tick: dict[str, Any]) -> bool:
        direction = tick.get("direction", "BUY")
        obi_5 = float(tick.get("obi_5", 0.0))
        obi_threshold = float(tick.get("obi_threshold", 0.2))
        if direction == "BUY" and obi_5 < -obi_threshold:
            return False
        if direction == "SELL" and obi_5 > obi_threshold:
            return False
        return True
