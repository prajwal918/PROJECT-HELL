from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

ANCHORED_VWAP_ENABLED = os.getenv("ANCHORED_VWAP_ENABLED", "true").lower() == "true"
ANCHORED_VWAP_MEAN_REVERSION_PIPS = float(os.getenv("ANCHORED_VWAP_MEAN_REVERSION_PIPS", "15"))
ANCHORED_VWAP_BUY_BONUS = float(os.getenv("ANCHORED_VWAP_BUY_BONUS", "0.12"))
ANCHORED_VWAP_SELL_BONUS = float(os.getenv("ANCHORED_VWAP_SELL_BONUS", "0.10"))
ANCHORED_VWAP_SESSION_RESET_S = float(os.getenv("ANCHORED_VWAP_SESSION_RESET_S", "28800"))
ANCHORED_VWAP_WEEKLY_RESET_S = float(os.getenv("ANCHORED_VWAP_WEEKLY_RESET_S", "604800"))


class AnchoredVWAP:
    def __init__(self):
        self._enabled = ANCHORED_VWAP_ENABLED
        self._reversion_pips = ANCHORED_VWAP_MEAN_REVERSION_PIPS
        self._buy_bonus = ANCHORED_VWAP_BUY_BONUS
        self._sell_bonus = ANCHORED_VWAP_SELL_BONUS
        self._anchors = {}  # type: Dict[str, Dict[str, dict]]
        self._cumul = defaultdict(lambda: defaultdict(lambda: {"sum_pv": 0.0, "sum_vol": 0.0}))
        self._last_session_reset = defaultdict(float)
        self._last_weekly_reset = defaultdict(float)
        self._news_anchor_price = {}  # type: Dict[str, float]
        if not self._enabled:
            logger.info("AnchoredVWAP disabled via ANCHORED_VWAP_ENABLED=false")

    def _pip_size(self, symbol):
        if "JPY" in symbol or "6J" in symbol:
            return 0.01
        if "XAU" in symbol or "GC" in symbol:
            return 0.1
        if "BCO" in symbol or "CL" in symbol:
            return 0.01
        return 0.0001

    def _check_reset(self, symbol, anchor_type):
        now = time.time()
        if anchor_type == "session":
            if now - self._last_session_reset[symbol] > ANCHORED_VWAP_SESSION_RESET_S:
                self._cumul[symbol]["session"] = {"sum_pv": 0.0, "sum_vol": 0.0}
                self._last_session_reset[symbol] = now
        elif anchor_type == "weekly":
            if now - self._last_weekly_reset[symbol] > ANCHORED_VWAP_WEEKLY_RESET_S:
                self._cumul[symbol]["weekly"] = {"sum_pv": 0.0, "sum_vol": 0.0}
                self._last_weekly_reset[symbol] = now

    def set_anchor(self, symbol, anchor_type, price):
        if not self._enabled:
            return
        if symbol not in self._anchors:
            self._anchors[symbol] = {}
        self._anchors[symbol][anchor_type] = {"price": price, "time": time.time()}
        self._cumul[symbol][anchor_type] = {"sum_pv": 0.0, "sum_vol": 0.0}
        if anchor_type == "session":
            self._last_session_reset[symbol] = time.time()
        elif anchor_type == "weekly":
            self._last_weekly_reset[symbol] = time.time()
        logger.debug("AnchoredVWAP anchor set: %s %s @ %.5f", symbol, anchor_type, price)

    def on_tick(self, symbol, mid, volume):
        if not self._enabled:
            return
        if volume <= 0:
            return
        if symbol not in self._anchors:
            return
        for anchor_type in self._anchors[symbol]:
            self._check_reset(symbol, anchor_type)
            c = self._cumul[symbol][anchor_type]
            c["sum_pv"] += mid * volume
            c["sum_vol"] += volume

    def get_vwap(self, symbol, anchor_type):
        c = self._cumul[symbol].get(anchor_type, {"sum_pv": 0.0, "sum_vol": 0.0})
        if c["sum_vol"] == 0:
            anchor = self._anchors.get(symbol, {}).get(anchor_type, {})
            return anchor.get("price", 0.0)
        return c["sum_pv"] / c["sum_vol"]

    def get_deviation(self, symbol, anchor_type):
        vwap = self.get_vwap(symbol, anchor_type)
        if vwap == 0.0:
            return 0.0
        c = self._cumul[symbol].get(anchor_type, {"sum_pv": 0.0, "sum_vol": 0.0})
        if c["sum_vol"] == 0:
            return 0.0
        last_price = c["sum_pv"] / c["sum_vol"]
        pip = self._pip_size(symbol)
        return (last_price - vwap) / pip

    def get_bonus(self, symbol, direction, mid):
        if not self._enabled:
            return 0.0
        pip = self._pip_size(symbol)
        bonus = 0.0
        for anchor_type in self._anchors.get(symbol, {}):
            vwap = self.get_vwap(symbol, anchor_type)
            if vwap == 0.0:
                continue
            deviation_pips = (mid - vwap) / pip
            if direction == "BUY" and deviation_pips < -self._reversion_pips:
                bonus = max(bonus, self._buy_bonus)
                logger.debug(
                    "AnchoredVWAP %s BUY bonus: %.1f pips below %s VWAP (%.5f)",
                    symbol, deviation_pips, anchor_type, vwap,
                )
            elif direction == "SELL" and deviation_pips > self._reversion_pips:
                bonus = max(bonus, self._sell_bonus)
                logger.debug(
                    "AnchoredVWAP %s SELL bonus: %.1f pips above %s VWAP (%.5f)",
                    symbol, deviation_pips, anchor_type, vwap,
                )
        return bonus

    def set_news_anchor(self, symbol, price):
        if not self._enabled:
            return
        self.set_anchor(symbol, "news", price)
        self._news_anchor_price[symbol] = price


anchored_vwap = AnchoredVWAP()
