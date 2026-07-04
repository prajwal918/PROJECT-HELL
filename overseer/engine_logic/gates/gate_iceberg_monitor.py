from __future__ import annotations

import logging
import os
from collections import defaultdict
from typing import Any

from .base_gate import BaseGate

LOGGER = logging.getLogger("overseer.gate_iceberg_monitor")

_ICEBERG_TRADE_RATIO = float(os.getenv("ICEBERG_TRADE_RATIO", "2.0"))
_ICEBERG_MIN_REPLENISHES = int(os.getenv("ICEBERG_MIN_REPLENISHES", "3"))


class GateIcebergMonitor(BaseGate):
    gate_name = "gate_iceberg_monitor"
    priority = 32

    def __init__(self) -> None:
        self._trade_volume_at_price: dict[str, dict[float, float]] = defaultdict(lambda: defaultdict(float))
        self._original_size_at_price: dict[str, dict[float, float]] = defaultdict(lambda: defaultdict(float))
        self._replenish_count: dict[str, dict[float, int]] = defaultdict(lambda: defaultdict(int))

    def update_from_tick(self, symbol: str, dom: dict) -> None:
        bids = dom.get("bids", [])
        asks = dom.get("asks", [])
        for b in bids:
            bp = float(b.get("price", b.get("Price", 0)))
            bs = float(b.get("size", b.get("Size", 0)))
            if bp not in self._original_size_at_price[symbol] or self._original_size_at_price[symbol][bp] == 0:
                self._original_size_at_price[symbol][bp] = bs

        for a in asks:
            ap = float(a.get("price", a.get("Price", 0)))
            a_s = float(a.get("size", a.get("Size", 0)))
            if ap not in self._original_size_at_price[symbol] or self._original_size_at_price[symbol][ap] == 0:
                self._original_size_at_price[symbol][ap] = a_s

    def record_trade(self, symbol: str, price: float, volume: float) -> None:
        self._trade_volume_at_price[symbol][price] += volume

        original = self._original_size_at_price[symbol].get(price, 0)
        if original > 0 and self._trade_volume_at_price[symbol][price] > original * _ICEBERG_TRADE_RATIO:
            self._replenish_count[symbol][price] += 1

    def evaluate(self, tick: dict[str, Any]) -> bool:
        symbol = tick.get("symbol", "")
        direction = tick.get("direction", "BUY")

        dom = tick.get("dom", {})
        if isinstance(dom, dict):
            self.update_from_tick(symbol, dom)

        trade_vol = float(tick.get("mw_tick_volume", 0))
        if trade_vol > 0:
            mid = (float(tick.get("bid", 0)) + float(tick.get("ask", 0))) / 2.0
            self.record_trade(symbol, mid, trade_vol)

        best_bid = float(tick.get("bid", 0))
        best_ask = float(tick.get("ask", 0))
        pip_size = float(tick.get("pip_size", 0.0001))

        bid_replenish = sum(
            1 for price, count in self._replenish_count.get(symbol, {}).items()
            if abs(price - best_bid) < pip_size * 5 and count >= _ICEBERG_MIN_REPLENISHES
        )
        ask_replenish = sum(
            1 for price, count in self._replenish_count.get(symbol, {}).items()
            if abs(price - best_ask) < pip_size * 5 and count >= _ICEBERG_MIN_REPLENISHES
        )

        if direction == "BUY" and bid_replenish > 0:
            return True
        if direction == "SELL" and ask_replenish > 0:
            return True

        return bid_replenish > 0 or ask_replenish > 0
