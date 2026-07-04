from __future__ import annotations

import logging
from typing import Any

from .base_gate import BaseGate

LOGGER = logging.getLogger("overseer.gate_HURST")

_HURST_MOMENTUM_THRESHOLD = float(__import__("os").getenv("HURST_MOMENTUM_THRESHOLD", "0.55"))
_HURST_MEANREV_THRESHOLD = float(__import__("os").getenv("HURST_MEANREV_THRESHOLD", "0.45"))
_HURST_MIN_CANDLES = int(__import__("os").getenv("HURST_MIN_CANDLES", "20"))


def _compute_hurst(prices: list[float]) -> float:
    if len(prices) < _HURST_MIN_CANDLES:
        return 0.5
    try:
        import math
        max_k = min(len(prices) // 2, 50)
        if max_k < 4:
            return 0.5
        rs_values = []
        for k in [4, 8, 16, 32]:
            if k > max_k:
                break
            n_sub = len(prices) // k
            if n_sub < 1:
                continue
            rs_sub = []
            for s in range(n_sub):
                chunk = prices[s * k:(s + 1) * k]
                if len(chunk) < k:
                    continue
                mean_val = sum(chunk) / len(chunk)
                deviations = [c - mean_val for c in chunk]
                cum_dev = [0.0]
                for d in deviations:
                    cum_dev.append(cum_dev[-1] + d)
                cum_dev = cum_dev[1:]
                r = max(cum_dev) - min(cum_dev)
                var = sum((d ** 2) for d in deviations) / len(deviations)
                if var > 0:
                    rs_sub.append(r / math.sqrt(var))
            if rs_sub:
                rs_values.append((math.log(k), math.log(sum(rs_sub) / len(rs_sub))))
        if len(rs_values) < 2:
            return 0.5
        n = len(rs_values)
        sum_x = sum(x for x, _ in rs_values)
        sum_y = sum(y for _, y in rs_values)
        sum_xy = sum(x * y for x, y in rs_values)
        sum_x2 = sum(x * x for x, _ in rs_values)
        denom = n * sum_x2 - sum_x * sum_x
        if abs(denom) < 1e-10:
            return 0.5
        slope = (n * sum_xy - sum_x * sum_y) / denom
        return max(0.0, min(1.0, slope))
    except Exception:
        return 0.5


class GateHurst(BaseGate):
    gate_name = "gate_HURST"
    priority = 35

    def evaluate(self, tick: dict[str, Any]) -> bool:
        direction = tick.get("direction", "BUY")
        candles = tick.get("_candles_1h", [])
        if not candles or len(candles) < _HURST_MIN_CANDLES:
            candles = tick.get("_candles_15m", [])
        if not candles or len(candles) < _HURST_MIN_CANDLES:
            return False

        closes = []
        for c in candles:
            if isinstance(c, dict):
                cv = float(c.get("close", 0))
                if cv > 0:
                    closes.append(cv)
        if len(closes) < _HURST_MIN_CANDLES:
            return False

        returns = []
        for i in range(1, len(closes)):
            if closes[i - 1] > 0:
                returns.append((closes[i] - closes[i - 1]) / closes[i - 1])

        if not returns:
            return False

        h = _compute_hurst(returns)
        tick["_hurst_value"] = round(h, 4)

        if direction == "BUY" and h > _HURST_MOMENTUM_THRESHOLD:
            return True
        if direction == "SELL" and h > _HURST_MOMENTUM_THRESHOLD:
            return True

        return False
