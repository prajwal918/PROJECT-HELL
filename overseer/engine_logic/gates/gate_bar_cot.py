from __future__ import annotations

import logging
import os
from typing import Any

from .base_gate import BaseGate

LOGGER = logging.getLogger("overseer.gate_bar_cot")

_COT_BULLISH_THRESHOLD = float(os.getenv("BAR_COT_BULLISH_THRESHOLD", "0.25"))
_COT_BEARISH_THRESHOLD = float(os.getenv("BAR_COT_BEARISH_THRESHOLD", "0.75"))


class GateBarCot(BaseGate):
    gate_name = "gate_bar_cot"
    priority = 33

    def __init__(self) -> None:
        self._candle_ticks: dict[str, list[dict]] = {}
        self._last_poc_result: dict[str, dict[str, Any]] = {}

    def process_candle_close(self, symbol: str, candle_open: float, candle_high: float, candle_low: float, candle_close: float, dom: dict) -> dict[str, Any]:
        bids = dom.get("bids", [])
        asks = dom.get("asks", [])
        price_volumes: dict[float, float] = {}

        for b in bids:
            bp = float(b.get("price", b.get("Price", 0)))
            bs = float(b.get("size", b.get("Size", 0)))
            price_volumes[bp] = price_volumes.get(bp, 0) + bs

        for a in asks:
            ap = float(a.get("price", a.get("Price", 0)))
            a_s = float(a.get("size", a.get("Size", 0)))
            price_volumes[ap] = price_volumes.get(ap, 0) + a_s

        if not price_volumes:
            return {"cot_position": 0.5, "signal": "NEUTRAL"}

        poc_price = max(price_volumes, key=price_volumes.get)
        candle_range = candle_high - candle_low
        if candle_range <= 0:
            return {"cot_position": 0.5, "signal": "NEUTRAL"}

        relative_position = (poc_price - candle_low) / candle_range

        signal = "NEUTRAL"
        if relative_position < _COT_BULLISH_THRESHOLD and candle_close > candle_open:
            signal = "PASSIVE_BUYERS_CONFIRMED"
        elif relative_position > _COT_BEARISH_THRESHOLD and candle_close < candle_open:
            signal = "PASSIVE_SELLERS_CONFIRMED"

        result = {"cot_position": round(relative_position, 4), "signal": signal, "poc_price": poc_price}
        self._last_poc_result[symbol] = result
        return result

    def evaluate(self, tick: dict[str, Any]) -> bool:
        symbol = tick.get("symbol", "")
        direction = tick.get("direction", "BUY")
        result = self._last_poc_result.get(symbol)

        if result is None:
            return True

        signal = result.get("signal", "NEUTRAL")
        if signal == "NEUTRAL":
            return True

        if direction == "BUY" and signal == "PASSIVE_BUYERS_CONFIRMED":
            return True
        if direction == "SELL" and signal == "PASSIVE_SELLERS_CONFIRMED":
            return True

        return True
