#!/usr/bin/env python3
"""
Initial Balance Breakout Quality — the first hour of each
session defines the day's character.

London 7:00-8:00 UTC, NY 13:30-14:30 UTC.

WIDE IB (>1.5x average) = trend day — trust momentum signals.
NARROW IB (<0.5x average) = coiled spring — wait for breakout,
then trade the breakout direction with a bonus.

Signal above IB high = breakout confirmed, +0.06 bonus.
Signal below IB low = breakout confirmed, +0.06 bonus.
Inside IB = no edge, neutral.
"""

import logging
import os
from collections import deque
from datetime import datetime, timezone
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np

LOGGER = logging.getLogger("overseer.initial_balance")

INITIAL_BALANCE_ENABLED = os.getenv(
    "INITIAL_BALANCE_ENABLED", "true"
).lower() in ("true", "1", "yes")

IB_BONUS = float(os.getenv("INITIAL_BALANCE_BONUS", "0.06"))
IB_WIDE_MULTIPLIER = float(os.getenv("IB_WIDE_MULTIPLIER", "1.5"))
IB_NARROW_MULTIPLIER = float(os.getenv("IB_NARROW_MULTIPLIER", "0.5"))
IB_BASELINE_DAYS = int(os.getenv("IB_BASELINE_DAYS", "20"))
IB_INSIDE_PENALTY = float(os.getenv("IB_INSIDE_PENALTY", "0.02"))

# Session definitions (UTC hours)
IB_SESSIONS = {
    "london": {"start": 7, "end": 8, "label": "London IB"},
    "new_york": {"start": 13, "end": 14, "label": "NY IB"},  # 13:30-14:30 handled inside
}


class _SymbolIB:
    """Per-symbol Initial Balance tracker."""

    __slots__ = (
        "ib_high",
        "ib_low",
        "ib_range",
        "session",
        "date_str",
        "in_ib_window",
        "ib_complete",
        "ib_bars",
        "historical_ranges",
    )

    def __init__(self):
        self.ib_high: float = 0.0
        self.ib_low: float = 999999.0
        self.ib_range: float = 0.0
        self.session: Optional[str] = None
        self.date_str: str = ""
        self.in_ib_window: bool = False
        self.ib_complete: bool = False
        self.ib_bars: int = 0
        self.historical_ranges: Deque[float] = deque(maxlen=IB_BASELINE_DAYS)


class InitialBalance:
    """Track Initial Balance per session per symbol."""

    def __init__(self):
        self._state: Dict[str, _SymbolIB] = {}

    def _get_state(self, symbol: str) -> _SymbolIB:
        if symbol not in self._state:
            self._state[symbol] = _SymbolIB()
        return self._state[symbol]

    def _check_ib_window(self, timestamp: datetime) -> Tuple[bool, Optional[str]]:
        """Check if we're currently in an IB window."""
        h = timestamp.hour
        m = timestamp.minute

        # London 7:00-8:00
        if h == 7:
            return True, "london"

        # NY 13:30-14:30
        if h == 13 and m >= 30:
            return True, "new_york"
        if h == 14 and m < 30:
            return True, "new_york"

        return False, None

    def on_tick(self, symbol: str, mid: float, timestamp: datetime) -> None:
        """
        Process a tick for IB tracking.

        During the IB window, tracks the high and low.
        When the IB window closes, finalizes the range.
        """
        if not INITIAL_BALANCE_ENABLED:
            return
        if mid <= 0:
            return

        state = self._get_state(symbol)
        today_str = timestamp.strftime("%Y-%m-%d")

        in_ib, session = self._check_ib_window(timestamp)

        # Day rollover — store yesterday's IB range and reset
        if today_str != state.date_str and state.date_str and state.ib_complete:
            if state.ib_range > 0:
                state.historical_ranges.append(state.ib_range)
            state.ib_complete = False
            state.ib_bars = 0
            state.ib_high = 0.0
            state.ib_low = 999999.0
            state.ib_range = 0.0

        if today_str != state.date_str:
            state.date_str = today_str
            state.session = None
            state.ib_complete = False
            state.ib_bars = 0
            state.ib_high = 0.0
            state.ib_low = 999999.0

        state.in_ib_window = in_ib

        if in_ib and session is not None:
            # Inside IB window — track high/low
            state.session = session
            state.ib_high = max(state.ib_high, mid)
            state.ib_low = min(state.ib_low, mid)
            state.ib_bars += 1
        elif not in_ib and state.session is not None and not state.ib_complete:
            # Just exited IB window — finalize
            if state.ib_bars > 0:
                state.ib_range = state.ib_high - state.ib_low
                state.ib_complete = True
                LOGGER.debug(
                    "IB complete: %s %s range=%.5f high=%.5f low=%.5f",
                    symbol,
                    state.session,
                    state.ib_range,
                    state.ib_high,
                    state.ib_low,
                )

    def get_ib_quality(self, symbol: str) -> Dict:
        """
        Classify the IB quality for a symbol.

        Returns:
            quality: "WIDE" | "NARROW" | "NORMAL" | "PENDING" | "NONE"
            ratio: current_range / avg_range
            range: IB range in price units
        """
        if not INITIAL_BALANCE_ENABLED:
            return {"quality": "NONE", "ratio": 0.0, "range": 0.0}

        state = self._get_state(symbol)

        if not state.ib_complete:
            if state.in_ib_window:
                return {"quality": "PENDING", "ratio": 0.0, "range": 0.0}
            return {"quality": "NONE", "ratio": 0.0, "range": 0.0}

        if state.ib_range <= 0:
            return {"quality": "NONE", "ratio": 0.0, "range": 0.0}

        if len(state.historical_ranges) < 3:
            return {
                "quality": "NORMAL",
                "ratio": 1.0,
                "range": state.ib_range,
            }

        avg_range = float(np.mean(list(state.historical_ranges)))
        if avg_range <= 0:
            return {
                "quality": "NORMAL",
                "ratio": 1.0,
                "range": state.ib_range,
            }

        ratio = state.ib_range / avg_range

        if ratio > IB_WIDE_MULTIPLIER:
            quality = "WIDE"
        elif ratio < IB_NARROW_MULTIPLIER:
            quality = "NARROW"
        else:
            quality = "NORMAL"

        return {
            "quality": quality,
            "ratio": round(ratio, 3),
            "range": state.ib_range,
            "ib_high": state.ib_high,
            "ib_low": state.ib_low,
            "session": state.session,
            "avg_range": round(avg_range, 5),
        }

    def get_breakout_bonus(
        self, symbol: str, direction: str, mid: float
    ) -> float:
        """
        Calculate bonus for a breakout signal.

        Signal above IB high with BUY: +IB_BONUS
        Signal below IB low with SELL: +IB_BONUS
        Inside IB: -IB_INSIDE_PENALTY (coiled spring, no edge yet)
        Wide IB + momentum: +IB_BONUS * 1.5 (trend day, trust it)
        """
        if not INITIAL_BALANCE_ENABLED:
            return 0.0

        state = self._get_state(symbol)
        if not state.ib_complete or state.ib_range <= 0:
            return 0.0

        ib_info = self.get_ib_quality(symbol)
        quality = ib_info.get("quality", "NONE")
        ib_high = state.ib_high
        ib_low = state.ib_low

        # Breakout above IB high
        if direction == "BUY" and mid > ib_high:
            if quality == "WIDE":
                return IB_BONUS * 1.5
            return IB_BONUS

        # Breakout below IB low
        if direction == "SELL" and mid < ib_low:
            if quality == "WIDE":
                return IB_BONUS * 1.5
            return IB_BONUS

        # Inside IB — no edge yet (coiled spring)
        if ib_low <= mid <= ib_high:
            if quality == "NARROW":
                return 0.0  # Coiled spring — breakout imminent, wait
            return -IB_INSIDE_PENALTY

        return 0.0

    def get_status(self, symbol: str) -> Dict:
        """Full status for dashboards."""
        state = self._get_state(symbol)
        quality = self.get_ib_quality(symbol)
        return {
            "enabled": INITIAL_BALANCE_ENABLED,
            "symbol": symbol,
            "ib_complete": state.ib_complete,
            "in_ib_window": state.in_ib_window,
            "ib_high": state.ib_high,
            "ib_low": state.ib_low,
            "ib_range": state.ib_range,
            "quality": quality.get("quality", "NONE"),
            "ratio": quality.get("ratio", 0.0),
            "session": state.session,
            "historical_days": len(state.historical_ranges),
        }

    def reset(self, symbol: Optional[str] = None) -> None:
        if symbol:
            self._state.pop(symbol, None)
        else:
            self._state.clear()


initial_balance = InitialBalance()
