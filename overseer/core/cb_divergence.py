from __future__ import annotations

import logging
import os
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

CB_DIVERGENCE_ENABLED = os.getenv("CB_DIVERGENCE_ENABLED", "true").lower() == "true"
CB_DIVERGENCE_BONUS = float(os.getenv("CB_DIVERGENCE_BONUS", "0.08"))
CB_DIVERGENCE_MIN_DELTA = float(os.getenv("CB_DIVERGENCE_MIN_DELTA", "0.10"))
CB_DIVERGENCE_HISTORY_LEN = int(os.getenv("CB_DIVERGENCE_HISTORY_LEN", "10"))

_CB_CURRENCIES = {
    "Fed": "USD", "ECB": "EUR", "BoE": "GBP", "BoJ": "JPY",
    "RBA": "AUD", "BOC": "CAD", "RBNZ": "NZD", "SNB": "CHF",
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


class CBDivergence:
    def __init__(self):
        self._enabled = CB_DIVERGENCE_ENABLED
        self._bonus = CB_DIVERGENCE_BONUS
        self._min_delta = CB_DIVERGENCE_MIN_DELTA
        self._history_len = CB_DIVERGENCE_HISTORY_LEN
        self._cb_scores = {}  # type: Dict[str, List[float]]
        self._rate_diffs = {}  # type: Dict[str, float]
        if not self._enabled:
            logger.info("CBDivergence disabled via CB_DIVERGENCE_ENABLED=false")

    def update_cb_score(self, cb_name, hawkishness):
        if not self._enabled:
            return
        if cb_name not in self._cb_scores:
            self._cb_scores[cb_name] = []
        self._cb_scores[cb_name].append(float(hawkishness))
        if len(self._cb_scores[cb_name]) > self._history_len:
            self._cb_scores[cb_name] = self._cb_scores[cb_name][-self._history_len:]
        logger.debug("CBDivergence: %s hawkishness=%.3f (history=%d)", cb_name, hawkishness, len(self._cb_scores[cb_name]))

    def update_rate_diff(self, cb_name, rate):
        self._rate_diffs[cb_name] = float(rate)

    def _get_cb_velocity(self, cb_name):
        history = self._cb_scores.get(cb_name, [])
        if len(history) < 2:
            return 0.0
        recent_avg = sum(history[-3:]) / min(len(history[-3:]), 3)
        older = history[:-3] if len(history) > 3 else [history[0]]
        older_avg = sum(older) / len(older)
        return recent_avg - older_avg

    def _get_base_quote_cbs(self, symbol):
        base_ccy = _PAIR_BASE.get(symbol, "")
        quote_ccy = _PAIR_QUOTE.get(symbol, "")
        base_cb = None
        quote_cb = None
        for cb_name, ccy in _CB_CURRENCIES.items():
            if ccy == base_ccy:
                base_cb = cb_name
            if ccy == quote_ccy:
                quote_cb = cb_name
        return base_cb, quote_cb

    def compute_divergence(self, symbol):
        if not self._enabled:
            return 0.0
        base_cb, quote_cb = self._get_base_quote_cbs(symbol)
        if base_cb is None or quote_cb is None:
            return 0.0
        base_vel = self._get_cb_velocity(base_cb)
        quote_vel = self._get_cb_velocity(quote_cb)
        divergence = base_vel - quote_vel
        base_rate = self._rate_diffs.get(base_cb, 0.0)
        quote_rate = self._rate_diffs.get(quote_cb, 0.0)
        rate_component = (base_rate - quote_rate) / 10.0
        combined = divergence * 0.7 + rate_component * 0.3
        return float(combined)

    def get_tailwind(self, symbol):
        if not self._enabled:
            return None, 0.0
        div = self.compute_divergence(symbol)
        if abs(div) < self._min_delta:
            return None, 0.0
        base_ccy = _PAIR_BASE.get(symbol, "")
        is_usd_base = (base_ccy == "USD")
        if div > 0:
            direction = "BUY" if not is_usd_base else "SELL"
        else:
            direction = "SELL" if not is_usd_base else "BUY"
        strength = min(abs(div), 1.0)
        return direction, strength

    def get_bonus(self, symbol, direction):
        if not self._enabled:
            return 0.0
        tailwind_dir, strength = self.get_tailwind(symbol)
        if tailwind_dir is None:
            return 0.0
        if direction == tailwind_dir:
            return self._bonus * strength
        return 0.0


cb_divergence = CBDivergence()
