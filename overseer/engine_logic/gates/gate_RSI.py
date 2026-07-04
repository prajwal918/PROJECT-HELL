from __future__ import annotations

import os
from collections import deque
from typing import Any

import numpy as np

from .base_gate import BaseGate

_RSI_PERIOD = int(os.getenv("GATE_RSI_PERIOD", "14"))
_RSI_WINDOW = int(os.getenv("GATE_RSI_WINDOW", "100"))
_RSI_OVERBOUGHT = float(os.getenv("GATE_RSI_OVERBOUGHT", "70.0"))
_RSI_OVERSOLD = float(os.getenv("GATE_RSI_OVERSOLD", "30.0"))
_RSI_LOOKBACK = int(os.getenv("GATE_RSI_LOOKBACK", "20"))


class GateRSI(BaseGate):
    gate_name = "gate_RSI"
    priority = 30

    def __init__(self) -> None:
        self._mids: deque[float] = deque(maxlen=_RSI_WINDOW)
        self._prev_rsi: float | None = None

    def _compute_rsi(self) -> float | None:
        if len(self._mids) < _RSI_PERIOD + 1:
            return None
        prices = np.array(self._mids)
        changes = np.diff(prices[-(_RSI_PERIOD + 1):])
        gains = np.where(changes > 0, changes, 0.0)
        losses = np.where(changes < 0, -changes, 0.0)
        avg_gain = float(np.mean(gains))
        avg_loss = float(np.mean(losses))
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def evaluate(self, tick: dict[str, Any]) -> bool:
        bid = float(tick.get("bid", 0.0))
        ask = float(tick.get("ask", 0.0))
        if bid <= 0 or ask <= 0:
            return True
        mid = (bid + ask) / 2.0
        self._mids.append(mid)
        rsi = self._compute_rsi()
        if rsi is None:
            return True
        tick["rsi"] = rsi
        direction = tick.get("direction", "BUY")
        if direction == "BUY" and rsi > _RSI_OVERBOUGHT:
            return False
        if direction == "SELL" and rsi < _RSI_OVERSOLD:
            return False
        if self._prev_rsi is not None:
            prices = np.array(self._mids)
            n = len(prices)
            lookback = min(_RSI_LOOKBACK, n - 1)
            if lookback >= 5:
                recent_prices = prices[-lookback:]
                price_trend = recent_prices[-1] - recent_prices[0]
                rsi_trend = rsi - self._prev_rsi
                if direction == "BUY":
                    if price_trend > 0 and rsi_trend < 0:
                        return False
                if direction == "SELL":
                    if price_trend < 0 and rsi_trend > 0:
                        return False
        self._prev_rsi = rsi
        return True
