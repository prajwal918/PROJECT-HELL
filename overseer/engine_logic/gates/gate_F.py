from __future__ import annotations

from typing import Any

from .base_gate import BaseGate


class GateF(BaseGate):
    gate_name = "gate_F"
    priority = 6

    def evaluate(self, tick: dict[str, Any]) -> bool:
        direction = tick.get("direction", "BUY")
        mid_velocity = float(tick.get("mid_velocity", 0.0))
        velocity_threshold = float(tick.get("velocity_threshold", 0.0003))
        if direction == "BUY" and mid_velocity < -velocity_threshold:
            return False
        if direction == "SELL" and mid_velocity > velocity_threshold:
            return False
        return True
