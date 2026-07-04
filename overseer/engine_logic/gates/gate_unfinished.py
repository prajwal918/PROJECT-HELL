from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from .base_gate import BaseGate

LOGGER = logging.getLogger("overseer.gate_unfinished")

_UNFINISHED_CACHE_PATH = Path(__file__).resolve().parent.parent.parent / "logs" / "unfinished_business.json"
_UNFINISHED_TOLERANCE_PIPS = float(os.getenv("UNFINISHED_TOLERANCE_PIPS", "3.0"))


class GateUnfinished(BaseGate):
    gate_name = "gate_unfinished"
    priority = 30

    def __init__(self) -> None:
        self._unfinished: dict[str, list[float]] = {}

    def _load_cache(self) -> None:
        try:
            if _UNFINISHED_CACHE_PATH.exists():
                data = json.loads(_UNFINISHED_CACHE_PATH.read_text())
                if isinstance(data, dict):
                    self._unfinished = {k: [float(v) for v in vals] for k, vals in data.items() if isinstance(vals, list)}
        except Exception:
            self._unfinished = {}

    def _save_cache(self) -> None:
        try:
            _UNFINISHED_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            _UNFINISHED_CACHE_PATH.write_text(json.dumps(self._unfinished))
        except Exception:
            pass

    def update_candle(self, symbol: str, candle_high: float, candle_low: float, candle_close: float, dom: dict, pip_size: float = 0.0001) -> None:
        if symbol not in self._unfinished:
            self._unfinished[symbol] = []

        bids = dom.get("bids", [])
        asks = dom.get("asks", [])

        high_bid_vol = 0.0
        low_ask_vol = 0.0
        for b in bids:
            bp = float(b.get("price", b.get("Price", 0)))
            if abs(bp - candle_high) < pip_size:
                high_bid_vol += float(b.get("size", b.get("Size", 0)))

        for a in asks:
            ap = float(a.get("price", a.get("Price", 0)))
            if abs(ap - candle_low) < pip_size:
                low_ask_vol += float(a.get("size", a.get("Size", 0)))

        if high_bid_vol > 0 and candle_close < candle_high:
            self._unfinished[symbol].append(candle_high)

        if low_ask_vol > 0 and candle_close > candle_low:
            self._unfinished[symbol].append(candle_low)

        self._unfinished[symbol] = self._unfinished[symbol][-50:]
        self._save_cache()

    def evaluate(self, tick: dict[str, Any]) -> bool:
        if not self._unfinished:
            self._load_cache()

        symbol = tick.get("symbol", "")
        direction = tick.get("direction", "BUY")
        mid = (float(tick.get("bid", 0)) + float(tick.get("ask", 0))) / 2.0
        pip_size = float(tick.get("pip_size", 0.0001))
        targets = self._unfinished.get(symbol, [])

        if not targets:
            return True

        for target in targets:
            distance_pips = abs(mid - target) / pip_size if pip_size > 0 else 999
            if distance_pips < _UNFINISHED_TOLERANCE_PIPS:
                if direction == "BUY" and target > mid:
                    return True
                if direction == "SELL" and target < mid:
                    return True

        return True
