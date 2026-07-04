"""Wavelet Decomposition for OVERSEER v13.

Multi-scale price decomposition using PyWavelets (pywt):
- Level 1: ultra-short (2-4 ticks)
- Level 2: short (4-8 ticks)
- Level 3: medium (8-32 ticks)
- Level 4: long (32-128 ticks)
- Level 5: very long (128-256 ticks)

When all three time horizons (scalp=1-2, intraday=3, session=4-5)
are aligned in the same direction → +0.06 bonus.

Falls back to simple moving average comparison if pywt not installed.
"""

from __future__ import annotations

import logging
import math
import os
from collections import deque
from typing import Dict, List, Optional, Tuple

LOGGER = logging.getLogger("overseer.wavelet_decomp")

_ENABLED = os.getenv("WAVELET_DECOMP_ENABLED", "true").lower() == "true"
_BONUS = float(os.getenv("WAVELET_BONUS", "0.06"))
_MAX_PRICES = int(os.getenv("WAVELET_MAX_PRICES", "256"))
_WAVELET_NAME = os.getenv("WAVELET_NAME", "db4")
_MIN_PRICES = int(os.getenv("WAVELET_MIN_PRICES", "32"))

try:
    import pywt
    _HAS_PYWT = True
except ImportError:
    _HAS_PYWT = False
    LOGGER.info("pywt not installed — using SMA fallback for wavelet decomposition")

_SCALP_LEVELS = (1, 2)
_INTRADAY_LEVEL = 3
_SESSION_LEVELS = (4, 5)


class WaveletDecomposition:
    """Multi-scale wavelet decomposition for trend alignment detection."""

    def __init__(self) -> None:
        self._prices: Dict[str, deque] = {}
        self._alignment_cache: Dict[str, Tuple[str, float]] = {}
        self._cache_time: Dict[str, float] = {}
        self._CACHE_TTL = 5.0

    def _init_symbol(self, symbol: str) -> None:
        if symbol not in self._prices:
            self._prices[symbol] = deque(maxlen=_MAX_PRICES)

    def update(self, symbol: str, prices: List[float]) -> None:
        if not _ENABLED:
            return
        self._init_symbol(symbol)
        for p in prices:
            self._prices[symbol].append(p)
        self._alignment_cache.pop(symbol, None)

    def update_single(self, symbol: str, price: float) -> None:
        if not _ENABLED:
            return
        self._init_symbol(symbol)
        self._prices[symbol].append(price)
        self._cache_time.pop(symbol, None)

    def _get_trend_sma(self, prices: List[float], short_window: int, long_window: int) -> str:
        if len(prices) < long_window:
            return "neutral"
        short_ma = sum(prices[-short_window:]) / short_window
        long_ma = sum(prices[-long_window:]) / long_window
        threshold = abs(long_ma) * 0.0001 if long_ma != 0 else 0.00001
        if short_ma > long_ma + threshold:
            return "up"
        elif short_ma < long_ma - threshold:
            return "down"
        return "neutral"

    def _decompose_pywt(self, prices: List[float]) -> Dict[int, str]:
        result: Dict[int, str] = {}
        try:
            coeffs = pywt.waved(prices, _WAVELET_NAME, level=5)
            approx = coeffs[0]
            details = coeffs[1:]

            for level_idx, detail in enumerate(details, start=1):
                if len(detail) < 2:
                    result[level_idx] = "neutral"
                    continue
                recent = detail[-4:] if len(detail) >= 4 else detail
                avg = sum(recent) / len(recent)
                threshold = max(abs(avg) * 0.1, 1e-8)
                if avg > threshold:
                    result[level_idx] = "up"
                elif avg < -threshold:
                    result[level_idx] = "down"
                else:
                    result[level_idx] = "neutral"

            if len(approx) >= 2:
                recent_approx = approx[-4:] if len(approx) >= 4 else approx
                avg = sum(recent_approx) / len(recent_approx)
                slope = recent_approx[-1] - recent_approx[0]
                threshold = max(abs(avg) * 0.001, 1e-8)
                if slope > threshold:
                    result[6] = "up"
                elif slope < -threshold:
                    result[6] = "down"
                else:
                    result[6] = "neutral"
        except Exception as exc:
            LOGGER.debug("pywt decomposition failed: %s", exc)
        return result

    def _decompose_sma(self, prices: List[float]) -> Dict[int, str]:
        result: Dict[int, str] = {}
        n = len(prices)
        windows = {1: (2, 4), 2: (4, 8), 3: (8, 32), 4: (32, 128), 5: (64, min(128, n))}
        for level, (short_w, long_w) in windows.items():
            if n < long_w:
                result[level] = "neutral"
                continue
            result[level] = self._get_trend_sma(prices, short_w, long_w)
        return result

    def _compute_alignment(self, prices: List[float]) -> Tuple[str, float]:
        if len(prices) < _MIN_PRICES:
            return ("neutral", 0.0)

        if _HAS_PYWT:
            levels = self._decompose_pywt(prices)
        else:
            levels = self._decompose_sma(prices)

        scalp_dirs = [levels.get(l, "neutral") for l in _SCALP_LEVELS]
        intraday_dir = levels.get(_INTRADAY_LEVEL, "neutral")
        session_dirs = [levels.get(l, "neutral") for l in _SESSION_LEVELS]

        scalp_up = sum(1 for d in scalp_dirs if d == "up")
        scalp_down = sum(1 for d in scalp_dirs if d == "down")
        scalp_total = len(scalp_dirs)

        session_up = sum(1 for d in session_dirs if d == "up")
        session_down = sum(1 for d in session_dirs if d == "down")
        session_total = len(session_dirs)

        up_count = scalp_up + (1 if intraday_dir == "up" else 0) + session_up
        down_count = scalp_down + (1 if intraday_dir == "down" else 0) + session_down
        total = scalp_total + 1 + session_total

        if up_count == total:
            return ("up", 1.0)
        elif down_count == total:
            return ("down", 1.0)
        elif up_count >= total * 0.75:
            return ("up", 0.75)
        elif down_count >= total * 0.75:
            return ("down", 0.75)
        elif up_count >= total * 0.5:
            return ("up", 0.5)
        elif down_count >= total * 0.5:
            return ("down", 0.5)

        return ("neutral", 0.0)

    def get_alignment(self, symbol: str) -> Tuple[str, float]:
        if not _ENABLED:
            return ("neutral", 0.0)

        import time
        now = time.time()
        cached = self._alignment_cache.get(symbol)
        cached_t = self._cache_time.get(symbol, 0.0)
        if cached is not None and (now - cached_t) < self._CACHE_TTL:
            return cached

        prices = list(self._prices.get(symbol, []))
        alignment = self._compute_alignment(prices)
        self._alignment_cache[symbol] = alignment
        self._cache_time[symbol] = now
        return alignment

    def get_bonus(self, symbol: str) -> float:
        if not _ENABLED:
            return 0.0

        direction, strength = self.get_alignment(symbol)
        if strength >= 1.0:
            return _BONUS
        elif strength >= 0.75:
            return _BONUS * 0.5
        return 0.0

    def get_directional_bonus(self, symbol: str, trade_direction: str) -> float:
        if not _ENABLED:
            return 0.0

        wave_dir, strength = self.get_alignment(symbol)
        if wave_dir == "neutral":
            return 0.0

        if trade_direction == "BUY" and wave_dir == "up":
            if strength >= 1.0:
                return _BONUS
            elif strength >= 0.75:
                return _BONUS * 0.5
        elif trade_direction == "SELL" and wave_dir == "down":
            if strength >= 1.0:
                return _BONUS
            elif strength >= 0.75:
                return _BONUS * 0.5
        elif trade_direction == "BUY" and wave_dir == "down":
            return -_BONUS * 0.5 if strength >= 0.75 else 0.0
        elif trade_direction == "SELL" and wave_dir == "up":
            return -_BONUS * 0.5 if strength >= 0.75 else 0.0

        return 0.0


wavelet_decomp = WaveletDecomposition()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import random
    random.seed(42)
    prices = [1.085 + random.gauss(0, 0.0005) for _ in range(256)]
    for i in range(200, 256):
        prices[i] = prices[i] + (i - 200) * 0.0001
    wavelet_decomp.update("6EM6", prices)
    direction, strength = wavelet_decomp.get_alignment("6EM6")
    print(f"  6EM6 alignment: {direction} strength={strength:.2f}")
    print(f"  Bonus: {wavelet_decomp.get_bonus('6EM6'):.4f}")
    for d in ("BUY", "SELL"):
        b = wavelet_decomp.get_directional_bonus("6EM6", d)
        print(f"  6EM6 {d}: directional_bonus={b:+.4f}")
