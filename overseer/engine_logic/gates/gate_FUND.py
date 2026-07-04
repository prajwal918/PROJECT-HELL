"""Fundamental Direction Alignment Gate for OVERSEER v12.5.

Passes unless the trade direction strongly opposes the macro fundamental bias:
- BUY signal + strongly negative bias (< -0.30) → fail
- SELL signal + strongly positive bias (> +0.30) → fail
- All other cases → pass

Uses ml/fundamental_bias.py which aggregates:
- Interest rate differentials (FRED + ECB)
- Yield curve spreads
- News sentiment (Finnhub)

Part of FW19_fundamental framework.
"""

from __future__ import annotations

import logging
from typing import Any

from engine_logic.gates.base_gate import BaseGate
from ml.fundamental_bias import compute_fundamental_bias

LOGGER = logging.getLogger("overseer.gate_FUND")

_FUND_BLOCK_THRESHOLD = 0.30


class Gate(BaseGate):
    gate_name = "gate_FUND"
    priority = 9_000

    def evaluate(self, tick: dict[str, Any]) -> bool:
        symbol = tick.get("symbol", "")
        direction = tick.get("direction", "").upper()

        if not symbol or direction not in ("BUY", "SELL"):
            return True

        try:
            bias = compute_fundamental_bias(symbol)
        except Exception as exc:
            LOGGER.debug("Fundamental bias error for %s: %s", symbol, exc)
            return True

        if abs(bias) < _FUND_BLOCK_THRESHOLD:
            return True

        if direction == "BUY" and bias < -_FUND_BLOCK_THRESHOLD:
            return False
        if direction == "SELL" and bias > _FUND_BLOCK_THRESHOLD:
            return False

        return True
