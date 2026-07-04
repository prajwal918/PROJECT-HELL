from __future__ import annotations

import logging
import math
import os
from typing import Any, Dict, List, Optional, Tuple

LOGGER = logging.getLogger("overseer.bandit_params")

_ENABLED = os.getenv("BANDIT_PARAMS_ENABLED", "true").lower() == "true"
_ARMS = [float(x) for x in os.getenv("BANDIT_ARMS", "0.85,0.87,0.90,0.92,0.95").split(",") if x.strip()]
_PRIOR_ALPHA = float(os.getenv("BANDIT_PRIOR_ALPHA", "1.0"))
_PRIOR_BETA = float(os.getenv("BANDIT_PRIOR_BETA", "1.0"))
_EXPLORE_SCALE = float(os.getenv("BANDIT_EXPLORE_SCALE", "1.0"))
_MIN_SAMPLES = int(os.getenv("BANDIT_MIN_SAMPLES", "10"))


class BanditParams:
    def __init__(self) -> None:
        self._arms = _ARMS
        self._alpha: Dict[str, Dict[float, float]] = {}
        self._beta: Dict[str, Dict[float, float]] = {}
        self._counts: Dict[str, Dict[float, int]] = {}
        self._selected: Dict[str, float] = {}

    def _init_symbol(self, symbol: str) -> None:
        if symbol not in self._alpha:
            self._alpha[symbol] = {a: _PRIOR_ALPHA for a in self._arms}
            self._beta[symbol] = {a: _PRIOR_BETA for a in self._arms}
            self._counts[symbol] = {a: 0 for a in self._arms}

    def select_threshold(self, symbol: str) -> float:
        if not _ENABLED:
            return 0.85
        self._init_symbol(symbol)
        best_arm = self._arms[0]
        best_sample = -1.0
        total_counts = sum(self._counts[symbol].values())
        for arm in self._arms:
            a = self._alpha[symbol][arm]
            b = self._beta[symbol][arm]
            if a <= 0:
                a = 0.01
            if b <= 0:
                b = 0.01
            sample = np_random_beta(a, b)
            if sample > best_sample:
                best_sample = sample
                best_arm = arm
        self._selected[symbol] = best_arm
        LOGGER.debug("Bandit selected threshold %.2f for %s", best_arm, symbol)
        return best_arm

    def update_arm(self, symbol: str, threshold: float, won: bool) -> None:
        if not _ENABLED:
            return
        self._init_symbol(symbol)
        nearest = min(self._arms, key=lambda x: abs(x - threshold))
        if won:
            self._alpha[symbol][nearest] += 1.0
        else:
            self._beta[symbol][nearest] += 1.0
        self._counts[symbol][nearest] += 1

    def get_best_threshold(self, symbol: str) -> float:
        self._init_symbol(symbol)
        best_arm = self._arms[0]
        best_wr = -1.0
        for arm in self._arms:
            a = self._alpha[symbol][arm]
            b = self._beta[symbol][arm]
            total = a + b
            if total < 2:
                wr = 0.5
            else:
                wr = a / total
            if wr > best_wr:
                best_wr = wr
                best_arm = arm
        return best_arm

    def get_arm_stats(self, symbol: str) -> Dict[float, Dict[str, Any]]:
        self._init_symbol(symbol)
        result = {}
        for arm in self._arms:
            a = self._alpha[symbol][arm]
            b = self._beta[symbol][arm]
            total = a + b
            wr = a / total if total > 0 else 0.5
            result[arm] = {
                "alpha": round(a, 2),
                "beta": round(b, 2),
                "win_rate": round(wr, 4),
                "samples": self._counts[symbol].get(arm, 0),
            }
        return result

    def get_status(self) -> Dict[str, Any]:
        return {
            "enabled": _ENABLED,
            "arms": self._arms,
            "symbols_tracked": list(self._alpha.keys()),
        }


def np_random_beta(a: float, b: float) -> float:
    try:
        import numpy as np
        return float(np.random.beta(max(a, 0.01), max(b, 0.01)))
    except Exception:
        u1 = _uniform_random()
        u2 = _uniform_random()
        while u1 == 0.0:
            u1 = _uniform_random()
        while u2 == 0.0:
            u2 = _uniform_random()
        return u1


def _uniform_random() -> float:
    import random
    return random.random()


bandit_params = BanditParams()
