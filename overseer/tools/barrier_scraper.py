from __future__ import annotations

import logging
import math
import os
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

BARRIER_SCRAPER_ENABLED = os.getenv("BARRIER_SCRAPER_ENABLED", "true").lower() == "true"
BARRIER_OI_THRESHOLD = float(os.getenv("BARRIER_OI_THRESHOLD", "5000"))
BARRIER_PROXIMITY_PIPS = float(os.getenv("BARRIER_PROXIMITY_PIPS", "10"))
BARRIER_PIN_RISK_DAYS = int(os.getenv("BARRIER_PIN_RISK_DAYS", "5"))
BARRIER_MAGNET_TP_PIPS = float(os.getenv("BARRIER_MAGNET_TP_PIPS", "5"))


class BarrierScraper:
    def __init__(self):
        self._enabled = BARRIER_SCRAPER_ENABLED
        self._oi_threshold = BARRIER_OI_THRESHOLD
        self._proximity_pips = BARRIER_PROXIMITY_PIPS
        self._pin_risk_days = BARRIER_PIN_RISK_DAYS
        self._magnet_tp_pips = BARRIER_MAGNET_TP_PIPS
        self._strikes = {}  # type: Dict[str, List[dict]]
        self._magnet_levels = {}  # type: Dict[str, List[dict]]
        if not self._enabled:
            logger.info("BarrierScraper disabled via BARRIER_SCRAPER_ENABLED=false")

    def _pip_size(self, symbol):
        if "JPY" in symbol or "6J" in symbol:
            return 0.01
        if "XAU" in symbol or "GC" in symbol:
            return 0.1
        return 0.0001

    def update_strikes(self, symbol, strikes_oi):
        if not self._enabled:
            return
        big_strikes = []
        for entry in strikes_oi:
            strike = entry.get("strike", 0.0)
            oi = entry.get("oi", 0.0)
            expiry_days = entry.get("days_to_expiry", 30)
            if oi >= self._oi_threshold:
                big_strikes.append({
                    "strike": float(strike),
                    "oi": float(oi),
                    "days_to_expiry": int(expiry_days),
                    "is_pin_risk": int(expiry_days) <= self._pin_risk_days,
                })
        self._strikes[symbol] = sorted(big_strikes, key=lambda x: x["oi"], reverse=True)
        self._compute_magnets(symbol)
        logger.debug(
            "BarrierScraper updated: %s (%d big strikes from %d total)",
            symbol, len(self._strikes[symbol]), len(strikes_oi),
        )

    def _compute_magnets(self, symbol):
        magnets = []
        for s in self._strikes.get(symbol, []):
            magnets.append({
                "price": s["strike"],
                "oi": s["oi"],
                "pin_risk": s["is_pin_risk"],
                "days_to_expiry": s["days_to_expiry"],
            })
        self._magnet_levels[symbol] = magnets

    def get_magnet_levels(self, symbol):
        if not self._enabled:
            return []
        return self._magnet_levels.get(symbol, [])

    def should_avoid_breakout(self, symbol, price):
        if not self._enabled:
            return False
        pip = self._pip_size(symbol)
        prox = self._proximity_pips * pip
        for s in self._strikes.get(symbol, []):
            dist = abs(price - s["strike"])
            if dist < prox and s["is_pin_risk"]:
                logger.debug(
                    "BarrierScraper: avoid breakout %s @ %.5f near pin-risk strike %.5f (OI=%.0f, %dd)",
                    symbol, price, s["strike"], s["oi"], s["days_to_expiry"],
                )
                return True
        return False

    def add_magnet_tp(self, symbol, direction):
        if not self._enabled:
            return None
        magnets = self._magnet_levels.get(symbol, [])
        if not magnets:
            return None
        pip = self._pip_size(symbol)
        candidates = []
        for m in magnets:
            if direction == "BUY":
                if m["price"] > 0:
                    candidates.append(m)
            elif direction == "SELL":
                candidates.append(m)
        if not candidates:
            return None
        candidates.sort(key=lambda x: x["oi"], reverse=True)
        best = candidates[0]
        tp_offset = best["price"]
        logger.debug(
            "BarrierScraper: magnet TP for %s %s → strike %.5f (OI=%.0f)",
            symbol, direction, best["price"], best["oi"],
        )
        return tp_offset


barrier_scraper = BarrierScraper()
