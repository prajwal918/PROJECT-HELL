from __future__ import annotations

import logging
import os
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

CARRY_MONITOR_ENABLED = os.getenv("CARRY_MONITOR_ENABLED", "true").lower() == "true"
CARRY_MONITOR_FLIP_BONUS = float(os.getenv("CARRY_MONITOR_FLIP_BONUS", "0.06"))
CARRY_MONITOR_HISTORY_LEN = int(os.getenv("CARRY_MONITOR_HISTORY_LEN", "30"))
CARRY_MONITOR_FLIP_THRESHOLD = float(os.getenv("CARRY_MONITOR_FLIP_THRESHOLD", "0.0"))

_CURRENCY_RATES = {
    "USD": 0.0, "EUR": 0.0, "GBP": 0.0, "JPY": 0.0,
    "AUD": 0.0, "CAD": 0.0, "NZD": 0.0, "CHF": 0.0,
}

_PAIR_BASE = {
    "6E": "EUR", "6B": "GBP", "6J": "JPY", "6A": "AUD",
    "6C": "CAD", "6N": "NZD", "6S": "CHF",
    "EURUSD": "EUR", "GBPUSD": "GBP", "USDJPY": "JPY",
    "AUDUSD": "AUD", "USDCAD": "CAD", "NZDUSD": "NZD", "USDCHF": "CHF",
}

_PAIR_QUOTE = {
    "6E": "USD", "6B": "USD", "6J": "USD", "6A": "USD",
    "6C": "USD", "6N": "USD", "6S": "USD",
    "EURUSD": "USD", "GBPUSD": "USD", "USDJPY": "JPY",
    "AUDUSD": "USD", "USDCAD": "CAD", "NZDUSD": "NZD", "USDCHF": "CHF",
}


class CarryMonitor:
    def __init__(self):
        self._enabled = CARRY_MONITOR_ENABLED
        self._flip_bonus = CARRY_MONITOR_FLIP_BONUS
        self._history_len = CARRY_MONITOR_HISTORY_LEN
        self._flip_threshold = CARRY_MONITOR_FLIP_THRESHOLD
        self._rates = dict(_CURRENCY_RATES)
        self._carry_history = {}  # type: Dict[str, List[float]]
        self._carry_current = {}  # type: Dict[str, float]
        self._flip_detected = {}  # type: Dict[str, Optional[str]]
        if not self._enabled:
            logger.info("CarryMonitor disabled via CARRY_MONITOR_ENABLED=false")

    def update_rates(self, rates_dict):
        if not self._enabled:
            return
        for ccy, rate in rates_dict.items():
            self._rates[ccy] = float(rate)
        logger.debug("CarryMonitor rates updated: %s", rates_dict)

    def compute_carry(self, symbol):
        if not self._enabled:
            return 0.0
        base_ccy = _PAIR_BASE.get(symbol, "")
        quote_ccy = _PAIR_QUOTE.get(symbol, "")
        if not base_ccy or not quote_ccy:
            return 0.0
        base_rate = self._rates.get(base_ccy, 0.0)
        quote_rate = self._rates.get(quote_ccy, 0.0)
        base_is_usd_equiv = (base_ccy == "USD")
        if base_is_usd_equiv:
            carry = quote_rate - base_rate
        else:
            carry = base_rate - quote_rate
        return carry

    def detect_flip(self, symbol):
        if not self._enabled:
            return None
        current = self.compute_carry(symbol)
        self._carry_current[symbol] = current
        if symbol not in self._carry_history:
            self._carry_history[symbol] = []
        self._carry_history[symbol].append(current)
        if len(self._carry_history[symbol]) > self._history_len:
            self._carry_history[symbol] = self._carry_history[symbol][-self._history_len:]
        history = self._carry_history[symbol]
        if len(history) < 2:
            self._flip_detected[symbol] = None
            return None
        prev = history[-2]
        flipped_positive_to_negative = (prev > self._flip_threshold and current <= self._flip_threshold)
        flipped_negative_to_positive = (prev <= self._flip_threshold and current > self._flip_threshold)
        if flipped_positive_to_negative:
            base_ccy = _PAIR_BASE.get(symbol, "")
            unwind_dir = "SELL" if base_ccy != "USD" else "BUY"
            self._flip_detected[symbol] = unwind_dir
            logger.info(
                "CarryMonitor: FLIP detected for %s: carry %.4f→%.4f (unwind=%s)",
                symbol, prev, current, unwind_dir,
            )
            return unwind_dir
        elif flipped_negative_to_positive:
            base_ccy = _PAIR_BASE.get(symbol, "")
            attract_dir = "BUY" if base_ccy != "USD" else "SELL"
            self._flip_detected[symbol] = attract_dir
            logger.info(
                "CarryMonitor: FLIP detected for %s: carry %.4f→%.4f (attract=%s)",
                symbol, prev, current, attract_dir,
            )
            return attract_dir
        self._flip_detected[symbol] = None
        return None

    def get_bonus(self, symbol, direction):
        if not self._enabled:
            return 0.0
        flip_dir = self._flip_detected.get(symbol)
        if flip_dir is None:
            return 0.0
        if direction == flip_dir:
            return self._flip_bonus
        return 0.0


carry_monitor = CarryMonitor()
