import os
import logging
import numpy as np
from collections import deque

log = logging.getLogger(__name__)

_ENABLED = os.getenv("FOOTPRINT_PATTERNS_ENABLED", "true").lower() == "true"
_INITIATIVE_BONUS = float(os.getenv("FOOTPRINT_INITIATIVE_BONUS", "0.06"))
_TRAPPED_BONUS = float(os.getenv("FOOTPRINT_TRAPPED_BONUS", "0.05"))
_EXHAUSTION_BONUS = float(os.getenv("FOOTPRINT_EXHAUSTION_BONUS", "0.07"))
_DELTA_MULT = float(os.getenv("FOOTPRINT_DELTA_MULT", "2.0"))
_VOLUME_MULT = float(os.getenv("FOOTPRINT_VOLUME_MULT", "3.0"))


class FootprintPatterns:
    def __init__(self):
        self._deltas = {}
        self._volumes = {}
        self._candles = {}

    def on_candle(self, symbol, open_p, high, low, close, volume, delta):
        if symbol not in self._candles:
            self._candles[symbol] = deque(maxlen=5)
            self._deltas[symbol] = deque(maxlen=5)
            self._volumes[symbol] = deque(maxlen=5)
        self._candles[symbol].append({"open": open_p, "high": high, "low": low, "close": close})
        self._deltas[symbol].append(delta)
        self._volumes[symbol].append(volume)

    def detect_patterns(self, symbol, direction):
        if not _ENABLED:
            return 0.0
        candles = self._candles.get(symbol, deque())
        deltas = self._deltas.get(symbol, deque())
        volumes = self._volumes.get(symbol, deque())
        if len(candles) < 2:
            return 0.0
        bonus = 0.0
        c = candles[-1]
        prev_c = candles[-2]
        delta = deltas[-1] if deltas else 0
        vol = volumes[-1] if volumes else 1
        avg_vol = sum(volumes) / max(len(volumes), 1) if volumes else 1
        avg_delta = abs(sum(deltas) / max(len(deltas), 1)) if deltas else 1
        if (delta > avg_delta * _DELTA_MULT and
            abs(c["close"] - c["high"]) < (c["high"] - c["low"]) * 0.1 and
            c["close"] > prev_c["high"]):
            if direction == "BUY":
                bonus += _INITIATIVE_BONUS
        vol_at_high = vol * 0.5
        if (vol_at_high > avg_vol * _VOLUME_MULT and
            c["close"] < c["open"] and
            abs(c["high"] - c["close"]) > 2 * abs(c["close"] - c["open"])):
            if direction == "BUY":
                bonus += _TRAPPED_BONUS
        if (vol > avg_vol * _VOLUME_MULT and
            abs(c["close"] - c["open"]) < (c["high"] - c["low"]) * 0.3):
            if direction == "SELL":
                bonus += _EXHAUSTION_BONUS
        return bonus


footprint_patterns = FootprintPatterns()
