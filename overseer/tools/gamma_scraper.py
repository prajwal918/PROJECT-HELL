from __future__ import annotations

import logging
import math
import os
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

GAMMA_SCRAPER_ENABLED = os.getenv("GAMMA_SCRAPER_ENABLED", "true").lower() == "true"
GAMMA_SHORT_BONUS = float(os.getenv("GAMMA_SHORT_BONUS", "0.07"))
GAMMA_LONG_PENALTY = float(os.getenv("GAMMA_LONG_PENALTY", "0.05"))
GAMMA_CACHE_TTL_S = float(os.getenv("GAMMA_CACHE_TTL_S", "3600"))
GAMMA_STRIKE_TOLERANCE_PIPS = float(os.getenv("GAMMA_STRIKE_TOLERANCE_PIPS", "15"))


class GammaScraper:
    def __init__(self):
        self._enabled = GAMMA_SCRAPER_ENABLED
        self._short_bonus = GAMMA_SHORT_BONUS
        self._long_penalty = GAMMA_LONG_PENALTY
        self._cache_ttl = GAMMA_CACHE_TTL_S
        self._strike_tol = GAMMA_STRIKE_TOLERANCE_PIPS
        self._chains = {}  # type: Dict[str, dict]
        self._gamma_cache = {}  # type: Dict[str, dict]
        self._cache_time = {}  # type: Dict[str, float]
        if not self._enabled:
            logger.info("GammaScraper disabled via GAMMA_SCRAPER_ENABLED=false")

    def _pip_size(self, symbol):
        if "JPY" in symbol or "6J" in symbol:
            return 0.01
        if "XAU" in symbol or "GC" in symbol:
            return 0.1
        return 0.0001

    def update_chain(self, symbol, strikes, oi, delta, spot):
        if not self._enabled:
            return
        self._chains[symbol] = {
            "strikes": np.array(strikes, dtype=np.float64),
            "oi": np.array(oi, dtype=np.float64),
            "delta": np.array(delta, dtype=np.float64),
            "spot": float(spot),
            "time": time.time(),
        }
        self._compute_gamma(symbol)
        logger.debug("GammaScraper chain updated: %s (%d strikes)", symbol, len(strikes))

    def _compute_gamma(self, symbol):
        chain = self._chains.get(symbol)
        if chain is None:
            return
        strikes = chain["strikes"]
        oi_arr = chain["oi"]
        delta_arr = chain["delta"]
        spot = chain["spot"]
        pip = self._pip_size(symbol)
        dK = max(np.mean(np.abs(np.diff(strikes))), pip * 10)
        gamma_per_strike = np.zeros_like(strikes, dtype=np.float64)
        for i in range(len(strikes)):
            if dK > 0 and oi_arr[i] > 0:
                gamma_val = abs(delta_arr[i] * oi_arr[i]) / (spot * spot * dK)
                gamma_per_strike[i] = gamma_val * 100.0
        total_gamma = float(np.sum(gamma_per_strike * oi_arr))
        self._gamma_cache[symbol] = {
            "gamma_per_strike": gamma_per_strike,
            "total_net_gamma": total_gamma,
            "is_short_gamma": total_gamma < 0,
            "is_long_gamma": total_gamma > 0,
            "strike_gamma": dict(zip(strikes.tolist(), gamma_per_strike.tolist())),
        }
        self._cache_time[symbol] = time.time()

    def _estimate_from_iv(self, symbol, iv_data):
        spot = iv_data.get("spot", 0.0)
        atm_iv = iv_data.get("atm_iv", 0.0)
        if spot == 0.0 or atm_iv == 0.0:
            return
        pip = self._pip_size(symbol)
        n_strikes = 20
        dK = spot * atm_iv * math.sqrt(30 / 365.0) / 5.0
        strikes = [spot + (i - n_strikes // 2) * dK for i in range(n_strikes)]
        oi = [max(100.0 - abs(i - n_strikes // 2) * 10, 10.0) for i in range(n_strikes)]
        delta = []
        for k in strikes:
            m = (k - spot) / (spot * atm_iv * math.sqrt(30 / 365.0)) if atm_iv > 0 else 0.0
            d = 0.5 * (1.0 + math.erf(-m / math.sqrt(2.0)))
            delta.append(d)
        self.update_chain(symbol, strikes, oi, delta, spot)
        logger.info("GammaScraper: estimated gamma for %s from IV (spot=%.5f, iv=%.4f)", symbol, spot, atm_iv)

    def get_gamma_exposure(self, symbol, price):
        if not self._enabled:
            return {"total_net_gamma": 0.0, "is_short_gamma": False, "is_long_gamma": False}
        cached = self._gamma_cache.get(symbol)
        if cached is None:
            return {"total_net_gamma": 0.0, "is_short_gamma": False, "is_long_gamma": False}
        if time.time() - self._cache_time.get(symbol, 0) > self._cache_ttl:
            return {"total_net_gamma": 0.0, "is_short_gamma": False, "is_long_gamma": False}
        result = {
            "total_net_gamma": cached["total_net_gamma"],
            "is_short_gamma": cached["is_short_gamma"],
            "is_long_gamma": cached["is_long_gamma"],
        }
        pip = self._pip_size(symbol)
        tol = self._strike_tol * pip
        nearest_gamma = 0.0
        for strike, g in cached.get("strike_gamma", {}).items():
            if abs(price - strike) < tol:
                nearest_gamma = g
                break
        result["local_gamma"] = nearest_gamma
        result["local_short_gamma"] = nearest_gamma < 0
        return result

    def get_bonus(self, symbol, direction, price):
        if not self._enabled:
            return 0.0
        exposure = self.get_gamma_exposure(symbol, price)
        bonus = 0.0
        if exposure.get("is_short_gamma", False) or exposure.get("local_short_gamma", False):
            pip = self._pip_size(symbol)
            if direction == "BUY" and price > (self._chains.get(symbol, {}).get("spot", price) - self._strike_tol * pip):
                bonus += self._short_bonus
            elif direction == "SELL" and price < (self._chains.get(symbol, {}).get("spot", price) + self._strike_tol * pip):
                bonus += self._short_bonus
        if exposure.get("is_long_gamma", False):
            bonus -= self._long_penalty
        return float(np.clip(bonus, -self._long_penalty, self._short_bonus))


gamma_scraper = GammaScraper()
