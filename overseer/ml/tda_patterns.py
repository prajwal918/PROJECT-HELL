from __future__ import annotations

import logging
import math
import os
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

LOGGER = logging.getLogger("overseer.tda_patterns")

_ENABLED = os.getenv("TDA_PATTERNS_ENABLED", "true").lower() == "true"
_EMBEDDING_DIM = int(os.getenv("TDA_EMBEDDING_DIM", "8"))
_DELAY = int(os.getenv("TDA_DELAY", "3"))
_MAX_PRICES = int(os.getenv("TDA_MAX_PRICES", "200"))
_DRIFT_PENALTY = float(os.getenv("TDA_DRIFT_PENALTY", "0.05"))
_DRIFT_DISTANCE_THRESHOLD = float(os.getenv("TDA_DRIFT_DISTANCE_THRESHOLD", "0.4"))
_DRIFT_WINDOW = int(os.getenv("TDA_DRIFT_WINDOW", "50"))
_MAX_SYMBOLS = int(os.getenv("TDA_MAX_SYMBOLS", "20"))


class TDAPatterns:
    def __init__(self) -> None:
        self._prices: Dict[str, deque] = {}
        self._fingerprints: Dict[str, deque] = {}
        self._drift_detected: Dict[str, bool] = {}
        self._drift_score: Dict[str, float] = {}
        self._baseline_fingerprint: Dict[str, np.ndarray] = {}

    def update_prices(self, symbol: str, prices: List[float]) -> None:
        if not _ENABLED:
            return
        if symbol not in self._prices:
            if len(self._prices) >= _MAX_SYMBOLS:
                return
            self._prices[symbol] = deque(maxlen=_MAX_PRICES)
            self._fingerprints[symbol] = deque(maxlen=_DRIFT_WINDOW)
        for p in prices:
            self._prices[symbol].append(p)

    def _takens_embedding(self, series: np.ndarray) -> np.ndarray:
        n = len(series)
        m = _EMBEDDING_DIM
        d = _DELAY
        if n < m * d:
            return np.array([])
        n_vectors = n - (m - 1) * d
        embedded = np.empty((n_vectors, m), dtype=np.float64)
        for i in range(n_vectors):
            for j in range(m):
                embedded[i, j] = series[i + j * d]
        return embedded

    def _compute_persistence(self, embedded: np.ndarray) -> np.ndarray:
        if len(embedded) < 2:
            return np.array([])
        n = len(embedded)
        distances = np.zeros((n, n), dtype=np.float64)
        for i in range(n):
            for j in range(i + 1, n):
                d = np.linalg.norm(embedded[i] - embedded[j])
                distances[i, j] = d
                distances[j, i] = d
        edges = []
        for i in range(n):
            for j in range(i + 1, n):
                edges.append((distances[i, j], i, j))
        edges.sort(key=lambda x: x[0])
        parent = list(range(n))
        rank = [0] * n

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra == rb:
                return None
            if rank[ra] < rank[rb]:
                ra, rb = rb, ra
            parent[rb] = ra
            if rank[ra] == rank[rb]:
                rank[ra] += 1
            return (ra, rb)
        persistences = []
        for dist, u, v in edges:
            result = union(u, v)
            if result is not None:
                persistences.append(dist)
        if not persistences:
            return np.array([0.0])
        arr = np.array(persistences, dtype=np.float64)
        if arr.max() > 0:
            arr = arr / arr.max()
        return arr

    def _fingerprint(self, persistences: np.ndarray) -> np.ndarray:
        if len(persistences) == 0:
            return np.zeros(8, dtype=np.float64)
        n_bins = 8
        hist, _ = np.histogram(persistences, bins=n_bins, range=(0.0, 1.0))
        total = hist.sum()
        if total > 0:
            hist = hist.astype(np.float64) / total
        return hist

    def compute_topology(self, symbol: str) -> Optional[np.ndarray]:
        if not _ENABLED:
            return None
        if symbol not in self._prices:
            return None
        data = list(self._prices[symbol])
        if len(data) < _EMBEDDING_DIM * _DELAY + 5:
            return None
        series = np.array(data, dtype=np.float64)
        diffs = np.diff(series)
        if len(diffs) < 2:
            return None
        std = np.std(diffs)
        if std > 0:
            diffs = diffs / std
        embedded = self._takens_embedding(diffs)
        if len(embedded) < 3:
            return None
        n_sample = min(len(embedded), 40)
        indices = np.linspace(0, len(embedded) - 1, n_sample, dtype=int)
        sampled = embedded[indices]
        persistences = self._compute_persistence(sampled)
        fp = self._fingerprint(persistences)
        if symbol not in self._baseline_fingerprint:
            self._baseline_fingerprint[symbol] = fp.copy()
        self._fingerprints[symbol].append(fp)
        return fp

    def check_drift(self, symbol: str) -> Tuple[bool, float]:
        if not _ENABLED:
            return False, 0.0
        if symbol not in self._fingerprints or len(self._fingerprints[symbol]) < 3:
            self._drift_detected[symbol] = False
            self._drift_score[symbol] = 0.0
            return False, 0.0
        baseline = self._baseline_fingerprint.get(symbol)
        if baseline is None:
            self._drift_detected[symbol] = False
            self._drift_score[symbol] = 0.0
            return False, 0.0
        current = self._fingerprints[symbol][-1]
        dist = float(np.linalg.norm(current - baseline))
        self._drift_score[symbol] = dist
        drifted = dist > _DRIFT_DISTANCE_THRESHOLD
        self._drift_detected[symbol] = drifted
        if drifted:
            LOGGER.info(
                "TDA topology drift detected for %s: distance=%.4f > threshold=%.4f",
                symbol, dist, _DRIFT_DISTANCE_THRESHOLD,
            )
        return drifted, dist

    def get_confidence_penalty(self, symbol: str) -> float:
        if not _ENABLED:
            return 0.0
        if self._drift_detected.get(symbol, False):
            return _DRIFT_PENALTY
        return 0.0

    def get_status(self) -> Dict[str, Any]:
        return {
            "enabled": _ENABLED,
            "drift_detected": dict(self._drift_detected),
            "drift_scores": {k: round(v, 4) for k, v in self._drift_score.items()},
            "n_symbols": len(self._prices),
        }


tda_patterns = TDAPatterns()
