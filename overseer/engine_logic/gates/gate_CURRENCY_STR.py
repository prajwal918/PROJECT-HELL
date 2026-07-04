from __future__ import annotations

import logging
from typing import Any

from .base_gate import BaseGate

LOGGER = logging.getLogger("overseer.gate_CURRENCY_STR")

_STRENGTH_LOOKBACK = int(__import__("os").getenv("CURRENCY_STR_LOOKBACK", "20"))
_STRENGTH_THRESHOLD = float(__import__("os").getenv("CURRENCY_STR_THRESHOLD", "0.6"))


class GateCurrencyStr(BaseGate):
    gate_name = "gate_CURRENCY_STR"
    priority = 36

    _base_currencies = {
        "6E": "EUR", "6B": "GBP", "6J": "JPY", "6A": "AUD",
        "6C": "CAD", "6N": "NZD", "6S": "CHF",
    }
    _quote_is_usd = {"6E", "6B", "6A", "6N"}
    _base_is_usd = {"6J", "6C", "6S"}

    def evaluate(self, tick: dict[str, Any]) -> bool:
        direction = tick.get("direction", "BUY")
        symbol = tick.get("symbol", "")
        candles = tick.get("_candles_daily", [])
        if not candles or len(candles) < _STRENGTH_LOOKBACK:
            candles = tick.get("_candles_1h", [])
        if not candles or len(candles) < _STRENGTH_LOOKBACK:
            return False

        root = symbol[:2] if len(symbol) >= 2 else ""
        if root not in self._base_currencies:
            return False

        recent = candles[-_STRENGTH_LOOKBACK:]
        closes = []
        for c in recent:
            if isinstance(c, dict):
                cv = float(c.get("close", 0))
                if cv > 0:
                    closes.append(cv)

        if len(closes) < 5:
            return False

        pct_change = (closes[-1] - closes[0]) / closes[0] if closes[0] > 0 else 0.0

        currency = self._base_currencies.get(root, "")
        if not currency:
            return False

        base_strength = pct_change if root in self._quote_is_usd else -pct_change

        if direction == "BUY":
            if root in self._quote_is_usd:
                if base_strength > _STRENGTH_THRESHOLD * 0.01:
                    return True
            elif root in self._base_is_usd:
                if base_strength < -_STRENGTH_THRESHOLD * 0.01:
                    return True

        if direction == "SELL":
            if root in self._quote_is_usd:
                if base_strength < -_STRENGTH_THRESHOLD * 0.01:
                    return True
            elif root in self._base_is_usd:
                if base_strength > _STRENGTH_THRESHOLD * 0.01:
                    return True

        return False
