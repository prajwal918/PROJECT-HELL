from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

CURRENCY_NETWORK_ENABLED = os.getenv("CURRENCY_NETWORK_ENABLED", "true").lower() == "true"
CURRENCY_NETWORK_WINDOW = int(os.getenv("CURRENCY_NETWORK_WINDOW", "20"))
CURRENCY_NETWORK_CENTRAL_BONUS = float(os.getenv("CURRENCY_NETWORK_CENTRAL_BONUS", "0.04"))
CURRENCY_NETWORK_PERIPHERAL_PENALTY = float(os.getenv("CURRENCY_NETWORK_PERIPHERAL_PENALTY", "0.02"))
CURRENCY_NETWORK_REFRESH_S = float(os.getenv("CURRENCY_NETWORK_REFRESH_S", "3600"))

_CURRENCY_MAP = {
    "6E": "EUR", "6B": "GBP", "6J": "JPY", "6A": "AUD",
    "6C": "CAD", "6N": "NZD", "6S": "CHF", "6M": "MXN",
    "EURUSD": "EUR", "GBPUSD": "GBP", "USDJPY": "JPY",
    "AUDUSD": "AUD", "USDCAD": "CAD", "NZDUSD": "NZD", "USDCHF": "CHF",
}


class CurrencyNetwork:
    def __init__(self):
        self._enabled = CURRENCY_NETWORK_ENABLED
        self._window = CURRENCY_NETWORK_WINDOW
        self._central_bonus = CURRENCY_NETWORK_CENTRAL_BONUS
        self._peripheral_penalty = CURRENCY_NETWORK_PERIPHERAL_PENALTY
        self._refresh_s = CURRENCY_NETWORK_REFRESH_S
        self._returns = defaultdict(list)  # type: Dict[str, List[float]]
        self._centrality = {}  # type: Dict[str, float]
        self._adj_matrix = None  # type: Optional[np.ndarray]
        self._currencies = []  # type: List[str]
        self._last_compute_time = 0.0
        self._max_centrality = 0.0
        self._median_centrality = 0.0
        if not self._enabled:
            logger.info("CurrencyNetwork disabled via CURRENCY_NETWORK_ENABLED=false")

    def update_prices(self, symbol, returns):
        if not self._enabled:
            return
        ccy = _CURRENCY_MAP.get(symbol, "")
        if not ccy:
            return
        self._returns[ccy].append(float(returns))
        if len(self._returns[ccy]) > self._window:
            self._returns[ccy] = self._returns[ccy][-self._window:]

    def compute_centrality(self):
        if not self._enabled:
            return
        try:
            import networkx as nx
        except ImportError:
            logger.warning("CurrencyNetwork: networkx not installed, skipping centrality")
            return
        self._currencies = sorted([c for c, r in self._returns.items() if len(r) >= 5])
        if len(self._currencies) < 3:
            return
        n = len(self._currencies)
        ret_matrix = {}
        for ccy in self._currencies:
            arr = np.array(self._returns[ccy][-self._window:])
            ret_matrix[ccy] = arr
        corr = np.zeros((n, n))
        for i in range(n):
            for j in range(n):
                ci = self._currencies[i]
                cj = self._currencies[j]
                ri = ret_matrix[ci]
                rj = ret_matrix[cj]
                min_len = min(len(ri), len(rj))
                if min_len < 3:
                    corr[i][j] = 0.0
                    continue
                ri_slice = ri[-min_len:]
                rj_slice = rj[-min_len:]
                c = np.corrcoef(ri_slice, rj_slice)[0, 1]
                corr[i][j] = c if not np.isnan(c) else 0.0
        self._adj_matrix = np.abs(corr)
        G = nx.Graph()
        for i, ccy in enumerate(self._currencies):
            G.add_node(ccy)
        for i in range(n):
            for j in range(i + 1, n):
                weight = self._adj_matrix[i][j]
                if weight > 0.3:
                    G.add_edge(self._currencies[i], self._currencies[j], weight=weight)
        try:
            centrality_dict = nx.eigenvector_centrality(G, weight="weight", max_iter=500)
        except nx.PowerIterationFailedConvergence:
            logger.warning("CurrencyNetwork: eigenvector centrality did not converge, using degree")
            centrality_dict = nx.degree_centrality(G)
        self._centrality = {k: float(v) for k, v in centrality_dict.items()}
        vals = list(self._centrality.values())
        self._max_centrality = max(vals) if vals else 0.0
        sorted_vals = sorted(vals)
        mid = len(sorted_vals) // 2
        self._median_centrality = sorted_vals[mid] if sorted_vals else 0.0
        self._last_compute_time = time.time()
        logger.info(
            "CurrencyNetwork: centrality computed for %d currencies, top=%s (%.4f)",
            len(self._currencies),
            max(self._centrality, key=self._centrality.get) if self._centrality else "N/A",
            self._max_centrality,
        )

    def maybe_refresh(self):
        if not self._enabled:
            return
        if time.time() - self._last_compute_time > self._refresh_s:
            self.compute_centrality()

    def get_centrality_bonus(self, symbol):
        if not self._enabled:
            return 0.0
        self.maybe_refresh()
        ccy = _CURRENCY_MAP.get(symbol, "")
        if not ccy or ccy not in self._centrality:
            return 0.0
        c = self._centrality[ccy]
        if self._max_centrality == 0.0:
            return 0.0
        normalized = c / self._max_centrality
        if c >= self._median_centrality:
            bonus = self._central_bonus * normalized
        else:
            bonus = -self._peripheral_penalty * (1.0 - normalized)
        return float(bonus)


currency_network = CurrencyNetwork()
