from __future__ import annotations

from typing import Any

from .base_gate import BaseGate


class GateE(BaseGate):
    gate_name = "gate_E"
    priority = 5

    def evaluate(self, tick: dict[str, Any]) -> bool:
        spread_bps = float(tick.get("spread_bps", 0.0))
        spread_bps_max = float(tick.get("spread_bps_max", 5.0))
        if spread_bps > spread_bps_max:
            return False
        return True
