from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

MIN_KELLY_FRACTION = float(os.getenv("GATE_K_MIN_KELLY", "0.01"))


class GateK(BaseGate):
    gate_name = "gate_K"
    priority = 11

    def evaluate(self, tick: dict[str, Any]) -> bool:
        kelly_frac = float(tick.get("kelly_fraction", 0.0))
        if kelly_frac <= 0:
            return True
        return kelly_frac >= MIN_KELLY_FRACTION
