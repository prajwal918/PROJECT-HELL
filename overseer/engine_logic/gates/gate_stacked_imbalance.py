from __future__ import annotations

import logging
from typing import Any

from .base_gate import BaseGate

LOGGER = logging.getLogger("overseer.gate_stacked_imbalance")

_IMBALGE_RATIO = float(__import__("os").getenv("STACKED_IMBALANCE_RATIO", "3.0"))
_CONSECUTIVE_LEVELS = int(__import__("os").getenv("STACKED_IMBALANCE_LEVELS", "3"))


class GateStackedImbalance(BaseGate):
    gate_name = "gate_stacked_imbalance"
    priority = 29

    def evaluate(self, tick: dict[str, Any]) -> bool:
        dom = tick.get("dom", {})
        if not isinstance(dom, dict):
            return False
        bids = dom.get("bids", [])
        asks = dom.get("asks", [])
        if not bids or not asks:
            return False
        direction = tick.get("direction", "BUY")

        buy_imbalance_count = 0
        sell_imbalance_count = 0

        max_levels = min(len(asks), len(bids)) - 1
        for i in range(max_levels):
            ask_size = float(asks[i].get("size", asks[i].get("Size", 0)))
            bid_size = float(bids[i].get("size", bids[i].get("Size", 0)))

            if i + 1 < len(bids):
                next_bid_size = float(bids[i + 1].get("size", bids[i + 1].get("Size", 0)))
            else:
                next_bid_size = 0

            if i + 1 < len(asks):
                next_ask_size = float(asks[i + 1].get("size", asks[i + 1].get("Size", 0)))
            else:
                next_ask_size = 0

            if next_bid_size > 0 and ask_size >= _IMBALGE_RATIO * next_bid_size:
                buy_imbalance_count += 1
            else:
                buy_imbalance_count = 0

            if next_ask_size > 0 and bid_size >= _IMBALGE_RATIO * next_ask_size:
                sell_imbalance_count += 1
            else:
                sell_imbalance_count = 0

        if direction == "BUY" and buy_imbalance_count >= _CONSECUTIVE_LEVELS:
            return True
        if direction == "SELL" and sell_imbalance_count >= _CONSECUTIVE_LEVELS:
            return True

        return False
