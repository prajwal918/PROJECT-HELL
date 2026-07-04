from __future__ import annotations

import logging
from typing import Any

from .base_gate import BaseGate

LOGGER = logging.getLogger("overseer.gate_RETAIL_SENTIMENT")

_RETAIL_EXTREME_THRESHOLD = float(__import__("os").getenv("RETAIL_EXTREME_THRESHOLD", "0.70"))


class GateRetailSentiment(BaseGate):
    gate_name = "gate_RETAIL_SENTIMENT"
    priority = 39

    def evaluate(self, tick: dict[str, Any]) -> bool:
        direction = tick.get("direction", "BUY")
        symbol = tick.get("symbol", "")

        try:
            from tools.retail_sentiment import retail_sentiment
            sentiment = retail_sentiment.get_sentiment(symbol)
        except Exception:
            return False

        if not sentiment:
            return False

        long_pct = float(sentiment.get("long_pct", 0.5))
        short_pct = float(sentiment.get("short_pct", 0.5))

        if direction == "BUY" and short_pct >= _RETAIL_EXTREME_THRESHOLD:
            return True
        if direction == "SELL" and long_pct >= _RETAIL_EXTREME_THRESHOLD:
            return True

        return False
