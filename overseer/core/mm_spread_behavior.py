#!/usr/bin/env python3
"""
Market Maker Spread Behavior — read the DOM to infer
institutional direction from how MMs skew their quotes.

Market makers don't place bids and asks symmetrically.
When they expect price to go UP:
  - Ask-side spread widens (they don't want to sell cheap)
  - Bid-side spread tightens (they're happy to buy)

When they expect price to go DOWN:
  - Bid-side spread widens (they don't want to buy expensive)
  - Ask-side spread tightens (they're happy to sell)

When BOTH sides widen: MM is stepping back, uncertainty is
high — skip the trade entirely.

This is reading the MM's inventory risk as a signal.
"""

import logging
import os
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

import numpy as np

LOGGER = logging.getLogger("overseer.mm_spread_behavior")

MM_SPREAD_BEHAVIOR_ENABLED = os.getenv(
    "MM_SPREAD_BEHAVIOR_ENABLED", "true"
).lower() in ("true", "1", "yes")

MM_BASELINE_TICKS = int(os.getenv("MM_BASELINE_TICKS", "100"))
MM_ZSCORE_THRESHOLD = float(os.getenv("MM_ZSCORE_THRESHOLD", "1.5"))
MM_BONUS = float(os.getenv("MM_BONUS", "0.05"))
MM_BOTH_WIDEN_BLOCK = os.getenv(
    "MM_BOTH_WIDEN_BLOCK", "true"
).lower() in ("true", "1", "yes")
MM_MIN_BASELINE = int(os.getenv("MM_MIN_BASELINE", "30"))


class _SymbolState:
    """Per-symbol MM spread tracking."""

    __slots__ = (
        "bid_spreads",
        "ask_spreads",
        "last_bid",
        "last_ask",
        "last_bid_size",
        "last_ask_size",
        "last_mid",
        "directional_lean",
    )

    def __init__(self):
        self.bid_spreads: Deque[float] = deque(maxlen=MM_BASELINE_TICKS)
        self.ask_spreads: Deque[float] = deque(maxlen=MM_BASELINE_TICKS)
        self.last_bid: float = 0.0
        self.last_ask: float = 0.0
        self.last_bid_size: float = 0.0
        self.last_ask_size: float = 0.0
        self.last_mid: float = 0.0
        self.directional_lean: Optional[str] = None


class MMSpreadBehavior:
    """Track market maker spread asymmetry to infer direction."""

    def __init__(self):
        self._states: Dict[str, _SymbolState] = {}

    def _get_state(self, symbol: str) -> _SymbolState:
        if symbol not in self._states:
            self._states[symbol] = _SymbolState()
        return self._states[symbol]

    @staticmethod
    def _compute_bid_spread(
        bid: float, ask: float, bid_size: float, ask_size: float
    ) -> float:
        """
        Bid-side spread: distance from mid to the bid,
        weighted by relative depth.
        """
        if ask <= bid or bid <= 0:
            return 0.0
        mid = (bid + ask) / 2.0
        total_size = bid_size + ask_size
        if total_size <= 0:
            return ask - bid
        # Bid spread = how far bid is from mid, adjusted for depth imbalance
        bid_distance = mid - bid
        depth_skew = ask_size / total_size if total_size > 0 else 0.5
        return bid_distance * (1.0 + depth_skew)

    @staticmethod
    def _compute_ask_spread(
        bid: float, ask: float, bid_size: float, ask_size: float
    ) -> float:
        """
        Ask-side spread: distance from mid to the ask,
        weighted by relative depth.
        """
        if ask <= bid or ask <= 0:
            return 0.0
        mid = (bid + ask) / 2.0
        total_size = bid_size + ask_size
        if total_size <= 0:
            return ask - bid
        ask_distance = ask - mid
        depth_skew = bid_size / total_size if total_size > 0 else 0.5
        return ask_distance * (1.0 + depth_skew)

    def on_tick(
        self,
        symbol: str,
        bid: float,
        ask: float,
        bid_size: float,
        ask_size: float,
    ) -> None:
        """Process a tick and update MM spread tracking."""
        if not MM_SPREAD_BEHAVIOR_ENABLED:
            return

        if bid <= 0 or ask <= 0 or ask <= bid:
            return

        state = self._get_state(symbol)

        bid_spread = self._compute_bid_spread(bid, ask, bid_size, ask_size)
        ask_spread = self._compute_ask_spread(bid, ask, bid_size, ask_size)

        state.bid_spreads.append(bid_spread)
        state.ask_spreads.append(ask_spread)
        state.last_bid = bid
        state.last_ask = ask
        state.last_bid_size = bid_size
        state.last_ask_size = ask_size
        state.last_mid = (bid + ask) / 2.0

        # Evaluate directional lean
        self._evaluate_lean(symbol, state)

    def _evaluate_lean(self, symbol: str, state: _SymbolState) -> None:
        """Determine MM directional lean from recent spread behavior."""
        if len(state.bid_spreads) < MM_MIN_BASELINE:
            state.directional_lean = None
            return

        bid_arr = np.array(list(state.bid_spreads), dtype=float)
        ask_arr = np.array(list(state.ask_spreads), dtype=float)

        bid_mean = float(np.mean(bid_arr))
        bid_std = float(np.std(bid_arr))
        ask_mean = float(np.mean(ask_arr))
        ask_std = float(np.std(ask_arr))

        current_bid_spread = state.bid_spreads[-1] if state.bid_spreads else 0.0
        current_ask_spread = state.ask_spreads[-1] if state.ask_spreads else 0.0

        bid_z = (
            (current_bid_spread - bid_mean) / bid_std
            if bid_std > 1e-12
            else 0.0
        )
        ask_z = (
            (current_ask_spread - ask_mean) / ask_std
            if ask_std > 1e-12
            else 0.0
        )

        bid_widening = bid_z > MM_ZSCORE_THRESHOLD
        ask_widening = ask_z > MM_ZSCORE_THRESHOLD

        # Both widening = MM stepping back
        if bid_widening and ask_widening:
            state.directional_lean = "STEP_BACK"
            return

        # Ask widening = MM doesn't want to sell = expects UP
        if ask_widening and not bid_widening:
            state.directional_lean = "BUY"
            return

        # Bid widening = MM doesn't want to buy = expects DOWN
        if bid_widening and not ask_widening:
            state.directional_lean = "SELL"
            return

        state.directional_lean = None

    def get_directional_lean(
        self, symbol: str
    ) -> Tuple[Optional[str], float]:
        """
        Get current MM directional lean and bonus.

        Returns:
            (direction, bonus) where direction is "BUY", "SELL",
            "STEP_BACK", or None. bonus is +MM_BONUS if lean
            aligns, 0.0 otherwise. STEP_BACK returns ("STEP_BACK", 0.0).
        """
        if not MM_SPREAD_BEHAVIOR_ENABLED:
            return None, 0.0

        state = self._get_state(symbol)
        lean = state.directional_lean

        if lean == "STEP_BACK":
            return "STEP_BACK", 0.0

        if lean is None:
            return None, 0.0

        return lean, MM_BONUS

    def should_skip_trade(self, symbol: str) -> bool:
        """Check if MM is stepping back (both sides widening)."""
        if not MM_SPREAD_BEHAVIOR_ENABLED or not MM_BOTH_WIDEN_BLOCK:
            return False
        state = self._get_state(symbol)
        return state.directional_lean == "STEP_BACK"

    def get_status(self, symbol: str) -> Dict:
        """Full status for dashboards."""
        state = self._get_state(symbol)
        return {
            "enabled": MM_SPREAD_BEHAVIOR_ENABLED,
            "symbol": symbol,
            "directional_lean": state.directional_lean,
            "samples": len(state.bid_spreads),
            "last_mid": state.last_mid,
            "last_bid_size": state.last_bid_size,
            "last_ask_size": state.last_ask_size,
        }

    def reset(self, symbol: Optional[str] = None) -> None:
        if symbol:
            self._states.pop(symbol, None)
        else:
            self._states.clear()


mm_spread_behavior = MMSpreadBehavior()
