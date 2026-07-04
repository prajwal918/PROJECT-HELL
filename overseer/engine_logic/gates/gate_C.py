from __future__ import annotations

from typing import Any

from .base_gate import BaseGate


class GateC(BaseGate):
    gate_name = "gate_C"
    priority = 3

    def evaluate(self, tick: dict[str, Any]) -> bool:
        symbol = str(tick.get("symbol", ""))
        dxy_bias = tick.get("dxy_bias", "NEUTRAL")
        direction = tick.get("direction", "BUY")
        if "USD" not in symbol:
            return True
        if dxy_bias == "NEUTRAL":
            return True
        if symbol.endswith("USD"):
            return (direction == "BUY" and dxy_bias == "WEAK") or (direction == "SELL" and dxy_bias == "STRONG")
        if symbol.startswith("USD"):
            return (direction == "BUY" and dxy_bias == "STRONG") or (direction == "SELL" and dxy_bias == "WEAK")
        return True
