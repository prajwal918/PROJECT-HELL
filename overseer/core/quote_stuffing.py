#!/usr/bin/env python3
"""
Quote Stuffing Detection — HFT manipulation signal.

When HFT algorithms flood the DOM with phantom quotes to slow
down competing systems and create latency arbitrage opportunities,
the DOM update rate spikes far above baseline.

Detection: if quote_update_rate > 10x rolling baseline average,
stuffing is likely active. Recommend waiting 2-3 ticks for the
bombardment to subside before committing capital.
"""

import logging
import os
import time
from collections import deque
from typing import Deque, Dict, Optional, Tuple

LOGGER = logging.getLogger("overseer.quote_stuffing")

DOM_QUOTE_STUFFING_ENABLED = os.getenv("DOM_QUOTE_STUFFING_ENABLED", "true").lower() in (
    "true", "1", "yes",
)
BASELINE_WINDOW = int(os.getenv("QUOTE_STUFFING_BASELINE_WINDOW", "200"))
DETECTION_MULTIPLIER = float(os.getenv("QUOTE_STUFFING_DETECTION_MULTIPLIER", "10.0"))
MIN_BASELINE_TICKS = int(os.getenv("QUOTE_STUFFING_MIN_BASELINE_TICKS", "50"))
STUFFING_COOLDOWN_TICKS = int(os.getenv("QUOTE_STUFFING_COOLDOWN_TICKS", "3"))


class QuoteStuffingDetector:
    """Per-symbol quote stuffing detector using DOM update rate."""

    def __init__(self):
        self._timestamps: Dict[str, Deque[float]] = {}
        self._baselines: Dict[str, float] = {}
        self._stuffing_active: Dict[str, bool] = {}
        self._cooldown_remaining: Dict[str, int] = {}

    def _get_ts_deque(self, symbol: str) -> Deque[float]:
        if symbol not in self._timestamps:
            self._timestamps[symbol] = deque(maxlen=BASELINE_WINDOW)
        return self._timestamps[symbol]

    def _compute_rate(self, symbol: str) -> float:
        """Compute DOM update rate (updates/second) over the baseline window."""
        ts = self._timestamps.get(symbol)
        if ts is None or len(ts) < 2:
            return 0.0
        elapsed = ts[-1] - ts[0]
        if elapsed <= 0:
            return 0.0
        return len(ts) / elapsed

    def _update_baseline(self, symbol: str) -> float:
        """Rolling average update rate serves as the baseline."""
        ts = self._timestamps.get(symbol)
        if ts is None or len(ts) < MIN_BASELINE_TICKS:
            self._baselines[symbol] = 0.0
            return 0.0
        rate = self._compute_rate(symbol)
        baseline = self._baselines.get(symbol, 0.0)
        if baseline <= 0:
            self._baselines[symbol] = rate
        else:
            alpha = 0.05
            self._baselines[symbol] = baseline * (1.0 - alpha) + rate * alpha
        return self._baselines[symbol]

    def on_dom_update(self, symbol: str, tick_count: int) -> None:
        """Record a DOM update event for the symbol."""
        if not DOM_QUOTE_STUFFING_ENABLED:
            return
        ts = self._get_ts_deque(symbol)
        ts.append(time.monotonic())
        self._update_baseline(symbol)

    def check_stuffing(
        self, symbol: str, tick_count: int
    ) -> Tuple[bool, int]:
        """
        Check if quote stuffing is active for a symbol.

        Returns:
            (is_stuffing, wait_ticks) — if stuffing, recommended
            ticks to wait before trading.
        """
        if not DOM_QUOTE_STUFFING_ENABLED:
            return False, 0

        cooldown = self._cooldown_remaining.get(symbol, 0)
        if cooldown > 0:
            self._cooldown_remaining[symbol] = cooldown - 1
            return True, cooldown

        baseline = self._baselines.get(symbol, 0.0)
        if baseline <= 0:
            self._stuffing_active[symbol] = False
            return False, 0

        current_rate = self._compute_rate(symbol)
        if current_rate > baseline * DETECTION_MULTIPLIER:
            self._stuffing_active[symbol] = True
            self._cooldown_remaining[symbol] = STUFFING_COOLDOWN_TICKS
            LOGGER.warning(
                "Quote stuffing detected: %s rate=%.1f/s baseline=%.1f/s (%.1fx)",
                symbol,
                current_rate,
                baseline,
                current_rate / baseline if baseline > 0 else 0,
            )
            return True, STUFFING_COOLDOWN_TICKS

        self._stuffing_active[symbol] = False
        return False, 0

    def is_stuffing_active(self, symbol: str) -> bool:
        """Quick check if stuffing is currently active for a symbol."""
        return self._stuffing_active.get(symbol, False)

    def get_status(self, symbol: str) -> Dict:
        """Full status dict for dashboards and logging."""
        baseline = self._baselines.get(symbol, 0.0)
        current_rate = self._compute_rate(symbol)
        return {
            "enabled": DOM_QUOTE_STUFFING_ENABLED,
            "symbol": symbol,
            "current_rate": round(current_rate, 2),
            "baseline_rate": round(baseline, 2),
            "ratio": round(current_rate / baseline, 2) if baseline > 0 else 0.0,
            "stuffing_active": self._stuffing_active.get(symbol, False),
            "cooldown": self._cooldown_remaining.get(symbol, 0),
            "samples": len(self._timestamps.get(symbol, [])),
        }

    def reset(self, symbol: Optional[str] = None) -> None:
        """Reset state for a symbol or all symbols."""
        if symbol:
            self._timestamps.pop(symbol, None)
            self._baselines.pop(symbol, None)
            self._stuffing_active.pop(symbol, None)
            self._cooldown_remaining.pop(symbol, None)
        else:
            self._timestamps.clear()
            self._baselines.clear()
            self._stuffing_active.clear()
            self._cooldown_remaining.clear()


quote_stuffing_detector = QuoteStuffingDetector()
