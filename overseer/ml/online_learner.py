from __future__ import annotations

import logging
import math
import os
from typing import Any, Dict, List, Optional

import numpy as np

LOGGER = logging.getLogger("overseer.online_learner")

_ENABLED = os.getenv("ONLINE_LEARNER_ENABLED", "true").lower() == "true"
_N_FEATURES = int(os.getenv("ONLINE_LEARNER_N_FEATURES", "19"))
_ALPHA = float(os.getenv("ONLINE_LEARNER_ALPHA", "0.05"))
_BETA = float(os.getenv("ONLINE_LEARNER_BETA", "1.0"))
_L1 = float(os.getenv("ONLINE_LEARNER_L1", "0.1"))
_L2 = float(os.getenv("ONLINE_LEARNER_L2", "1.0"))
_BONUS_SCALE = float(os.getenv("ONLINE_LEARNER_BONUS_SCALE", "0.10"))
_MAX_BONUS = float(os.getenv("ONLINE_LEARNER_MAX_BONUS", "0.05"))


class FTRLOptimizer:
    def __init__(self) -> None:
        self._n = _N_FEATURES
        self._z = np.zeros(self._n, dtype=np.float64)
        self._n_grad = np.zeros(self._n, dtype=np.float64)
        self._weights = np.zeros(self._n, dtype=np.float64)
        self._n_updates = 0
        self._alpha = _ALPHA
        self._beta = _BETA
        self._l1 = _L1
        self._l2 = _L2

    def _sigmoid(self, x: float) -> float:
        if x >= 0:
            return 1.0 / (1.0 + math.exp(-x))
        ex = math.exp(x)
        return ex / (1.0 + ex)

    def predict(self, features: List[float]) -> float:
        if not _ENABLED:
            return 0.5
        if not features:
            return 0.5
        arr = np.array(features, dtype=np.float64)
        if len(arr) < self._n:
            padded = np.zeros(self._n, dtype=np.float64)
            padded[:len(arr)] = arr
            arr = padded
        elif len(arr) > self._n:
            arr = arr[:self._n]
        score = float(np.dot(self._weights, arr))
        return self._sigmoid(score)

    def update(self, features: List[float], label: int) -> None:
        if not _ENABLED:
            return
        if not features:
            return
        self._n_updates += 1
        arr = np.array(features, dtype=np.float64)
        if len(arr) < self._n:
            padded = np.zeros(self._n, dtype=np.float64)
            padded[:len(arr)] = arr
            arr = padded
        elif len(arr) > self._n:
            arr = arr[:self._n]
        p = self._sigmoid(float(np.dot(self._weights, arr)))
        g = (p - label) * arr
        sigma = (np.sqrt(self._n_grad + g * g) - np.sqrt(self._n_grad)) / self._alpha
        self._z += g - sigma * self._weights
        self._n_grad += g * g
        self._recompute_weights()

    def _recompute_weights(self) -> None:
        for i in range(self._n):
            z_i = self._z[i]
            n_i = self._n_grad[i]
            if abs(z_i) <= self._l1:
                self._weights[i] = 0.0
            else:
                sign = 1.0 if z_i > 0 else -1.0
                eta = (self._beta + math.sqrt(n_i)) / self._alpha
                self._weights[i] = (sign * self._l1 - z_i) / (eta + self._l2)

    def get_bonus(self, features: List[float]) -> float:
        if not _ENABLED:
            return 0.0
        pred = self.predict(features)
        bonus = (pred - 0.5) * 2.0 * _BONUS_SCALE
        bonus = max(-_MAX_BONUS, min(_MAX_BONUS, bonus))
        return bonus

    def get_weights(self) -> np.ndarray:
        return self._weights.copy()

    def get_status(self) -> Dict[str, Any]:
        return {
            "enabled": _ENABLED,
            "n_updates": self._n_updates,
            "n_features": self._n,
            "weight_norm": float(np.linalg.norm(self._weights)),
            "nonzero_weights": int(np.count_nonzero(self._weights)),
        }


online_learner = FTRLOptimizer()
