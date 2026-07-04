from __future__ import annotations

import os
from typing import Any

from .base_gate import BaseGate

MAX_DAILY_DRAWDOWN_PCT = float(os.getenv("GATE_R_MAX_DRAWDOWN_PCT", "2.0"))


class GateR(BaseGate):
    gate_name = "gate_R"
    priority = 18

    def evaluate(self, tick: dict[str, Any]) -> bool:
        drawdown_pct = float(tick.get("daily_drawdown_pct", 0.0))
        return drawdown_pct < MAX_DAILY_DRAWDOWN_PCT
