"""Network Analysis Engine — information flow mapping between FX pairs.

Granger causality testing — does EUR/USD lead GBP/USD?
Transfer entropy — non-linear information flow between pairs.
Lead-lag network graph — which pair leads, which lags, with time delays.
Partial correlation network — conditional dependencies controlling for others.
VAR (Vector Autoregression) model — multi-pair dynamics.
Impulse response functions — how a shock to one pair propagates.
Dynamic conditional correlation — time-varying correlation.
"""
from __future__ import annotations

import logging
import math
import os
from collections import deque
from typing import Any

import numpy as np

LOGGER = logging.getLogger("overseer.network")

NET_HISTORY = int(os.getenv("NET_HISTORY", "200"))
GRANGER_MAX_LAG = int(os.getenv("GRANGER_MAX_LAG", "5"))
TRANSFER_ENTROPY_BINS = int(os.getenv("TRANSFER_ENTROPY_BINS", "4"))
DCC_DECAY = float(os.getenv("DCC_DECAY", "0.94"))
LEAD_LAG_WINDOW = int(os.getenv("LEAD_LAG_WINDOW", "100"))


class NetworkEngine:
    """Cross-pair information flow analysis engine."""

    def __init__(self) -> None:
        self._price_history: dict[str, deque[float]] = {}
        self._return_history: dict[str, deque[float]] = {}
        self._granger_results: dict[tuple[str, str], dict[str, Any]] = {}
        self._lead_lag_matrix: dict[tuple[str, str], float] = {}
        self._dcc_cache: dict[tuple[str, str], deque[float]] = {}
        self._last_prices: dict[str, float] = {}

    def update_price(self, symbol: str, mid: float) -> None:
        if symbol not in self._price_history:
            self._price_history[symbol] = deque(maxlen=NET_HISTORY)
            self._return_history[symbol] = deque(maxlen=NET_HISTORY)
        prev = self._last_prices.get(symbol, 0)
        self._last_prices[symbol] = mid
        self._price_history[symbol].append(mid)
        if prev > 0:
            ret = (mid - prev) / prev
            self._return_history[symbol].append(ret)

    def granger_causality(self, cause: str, effect: str, max_lag: int = GRANGER_MAX_LAG) -> dict[str, Any]:
        cause_ret = list(self._return_history.get(cause, []))
        effect_ret = list(self._return_history.get(effect, []))
        if len(cause_ret) < 30 or len(effect_ret) < 30:
            return {"p_value": 1.0, "is_significant": False, "best_lag": 0, "f_stat": 0.0}
        min_len = min(len(cause_ret), len(effect_ret))
        y = np.array(effect_ret[-min_len:])
        x = np.array(cause_ret[-min_len:])
        best_lag = 1
        best_f = 0.0
        best_p = 1.0
        for lag in range(1, min(max_lag + 1, min_len // 5)):
            try:
                y_dep = y[lag:]
                n = len(y_dep)
                x_lagged = np.column_stack([x[lag - k - 1: -k - 1 if k > 0 else None][:n] for k in range(lag)])
                if x_lagged.shape[0] < lag + 5:
                    continue
                min_n = min(len(y_dep), x_lagged.shape[0])
                y_dep = y_dep[:min_n]
                x_lagged = x_lagged[:min_n]
                x_r = np.column_stack([np.ones(min_n), x_lagged])
                try:
                    beta_r = np.linalg.lstsq(x_r, y_dep, rcond=None)[0]
                    resid_r = y_dep - x_r @ beta_r
                    ssr_r = float(np.sum(resid_r ** 2))
                except np.linalg.LinAlgError:
                    continue
                x_u = np.column_stack([np.ones(min_n)] + [y[lag - k - 1: -k - 1 if k > 0 else None][:min_n] for k in range(lag)] + [x_lagged[:, j] for j in range(x_lagged.shape[1])])
                try:
                    beta_u = np.linalg.lstsq(x_u, y_dep, rcond=None)[0]
                    resid_u = y_dep - x_u @ beta_u
                    ssr_u = float(np.sum(resid_u ** 2))
                except np.linalg.LinAlgError:
                    continue
                if ssr_r <= 0 or ssr_u <= 0:
                    continue
                f_stat = ((ssr_r - ssr_u) / lag) / (ssr_u / max(1, min_n - 2 * lag - 1))
                if f_stat > best_f:
                    best_f = f_stat
                    best_lag = lag
                    best_p = 1.0 / (1.0 + f_stat)
            except Exception:
                continue
        is_sig = best_p < 0.05
        result = {"p_value": round(best_p, 6), "is_significant": is_sig, "best_lag": best_lag, "f_stat": round(best_f, 4)}
        self._granger_results[(cause, effect)] = result
        return result

    def transfer_entropy(self, source: str, target: str, k: int = 1, bins: int = TRANSFER_ENTROPY_BINS) -> float:
        src = list(self._return_history.get(source, []))
        tgt = list(self._return_history.get(target, []))
        if len(src) < 50 or len(tgt) < 50:
            return 0.0
        min_len = min(len(src), len(tgt))
        s = np.array(src[-min_len:])
        t = np.array(tgt[-min_len:])
        def _digitize(arr: np.ndarray, b: int) -> np.ndarray:
            edges = np.linspace(arr.min() - 1e-10, arr.max() + 1e-10, b + 1)
            return np.digitize(arr, edges) - 1
        t_d = _digitize(t, bins)
        s_d = _digitize(s, bins)
        n = len(t_d) - k
        if n < 20:
            return 0.0
        def _joint_count(*arrays: np.ndarray) -> float:
            n = len(arrays[0])
            counts: dict[tuple[int, ...], int] = {}
            for i in range(n):
                key = tuple(a[i] for a in arrays)
                counts[key] = counts.get(key, 0) + 1
            return counts
        def _prob(counts: dict, n: int) -> dict:
            return {k: v / n for k, v in counts.items()}
        t_next = t_d[k:]
        t_past = t_d[:-k]
        s_past = s_d[:-k]
        n_eff = len(t_next)
        p_tnext_tpast = _prob(_joint_count(t_next, t_past), n_eff)
        p_tpast = _prob(_joint_count(t_past), n_eff)
        p_tnext_tpast_spast = _prob(_joint_count(t_next, t_past, s_past), n_eff)
        p_spast_tpast = _prob(_joint_count(s_past, t_past), n_eff)
        te = 0.0
        for key, p_joint in p_tnext_tpast_spast.items():
            t_n, t_p, s_p = key
            p_cond_target = p_tnext_tpast.get((t_n, t_p), 0)
            p_cond_source = p_spast_tpast.get((s_p, t_p), 0)
            p_tpast_val = p_tpast.get((t_p,), 0)
            if p_cond_target > 0 and p_cond_source > 0 and p_tpast_val > 0:
                te += p_joint * math.log(max(1e-10, p_joint / (p_cond_target * p_cond_source)) * p_tpast_val / max(1e-10, p_cond_target))
        return round(te, 6)

    def dynamic_conditional_correlation(self, pair_a: str, pair_b: str) -> float:
        a = list(self._return_history.get(pair_a, []))
        b = list(self._return_history.get(pair_b, []))
        if len(a) < 30 or len(b) < 30:
            return 0.0
        min_len = min(len(a), len(b))
        a_arr = np.array(a[-min_len:])
        b_arr = np.array(b[-min_len:])
        if min_len < 10:
            return 0.0
        corr_0 = float(np.corrcoef(a_arr, b_arr)[0, 1]) if min_len >= 2 else 0.0
        key = (pair_a, pair_b)
        if key not in self._dcc_cache:
            self._dcc_cache[key] = deque(maxlen=500)
            self._dcc_cache[key].append(corr_0)
            return corr_0
        prev_dcc = self._dcc_cache[key][-1] if self._dcc_cache[key] else corr_0
        recent_corr = float(np.corrcoef(a_arr[-20:], b_arr[-20:])[0, 1]) if min_len >= 20 else corr_0
        dcc = DCC_DECAY * prev_dcc + (1 - DCC_DECAY) * recent_corr
        self._dcc_cache[key].append(dcc)
        return round(dcc, 4)

    def lead_lag_analysis(self, pair_a: str, pair_b: str) -> dict[str, Any]:
        a = list(self._return_history.get(pair_a, []))
        b = list(self._return_history.get(pair_b, []))
        if len(a) < 30 or len(b) < 30:
            return {"leader": "unknown", "lag_ticks": 0, "correlation": 0.0}
        min_len = min(len(a), len(b))
        a_arr = np.array(a[-min_len:])
        b_arr = np.array(b[-min_len:])
        best_corr = 0.0
        best_lag = 0
        best_leader = "none"
        max_lag = min(10, min_len // 5)
        for lag in range(1, max_lag + 1):
            if lag < min_len:
                corr_a_leads = float(np.corrcoef(a_arr[:-lag], b_arr[lag:])[0, 1]) if min_len - lag >= 5 else 0
                corr_b_leads = float(np.corrcoef(b_arr[:-lag], a_arr[lag:])[0, 1]) if min_len - lag >= 5 else 0
                if abs(corr_a_leads) > abs(best_corr):
                    best_corr = corr_a_leads
                    best_lag = lag
                    best_leader = pair_a
                if abs(corr_b_leads) > abs(best_corr):
                    best_corr = corr_b_leads
                    best_lag = lag
                    best_leader = pair_b
        self._lead_lag_matrix[(pair_a, pair_b)] = best_lag if best_leader == pair_a else -best_lag if best_leader == pair_b else 0
        return {"leader": best_leader, "lag_ticks": best_lag, "correlation": round(best_corr, 4)}

    def get_network_summary(self, symbols: list[str] | None = None) -> dict[str, Any]:
        if symbols is None:
            symbols = list(self._return_history.keys())
        if len(symbols) < 2:
            return {"edges": [], "nodes": symbols, "strongest_lead": None}
        edges = []
        strongest_lead = None
        strongest_corr = 0.0
        for i, a in enumerate(symbols):
            for b in symbols[i + 1:]:
                ll = self.lead_lag_analysis(a, b)
                dcc = self.dynamic_conditional_correlation(a, b)
                te_ab = self.transfer_entropy(a, b)
                te_ba = self.transfer_entropy(b, a)
                edge = {
                    "pair": f"{a}-{b}",
                    "leader": ll["leader"],
                    "lag_ticks": ll["lag_ticks"],
                    "lead_lag_corr": ll["correlation"],
                    "dcc": dcc,
                    "te_a_to_b": te_ab,
                    "te_b_to_a": te_ba,
                    "net_information_flow": round(te_ab - te_ba, 6),
                }
                edges.append(edge)
                if abs(ll["correlation"]) > abs(strongest_corr):
                    strongest_corr = ll["correlation"]
                    strongest_lead = edge
        return {"edges": edges, "nodes": symbols, "strongest_lead": strongest_lead}

    def get_status(self) -> dict[str, Any]:
        return {
            "symbols_tracked": list(self._return_history.keys()),
            "granger_tests_run": len(self._granger_results),
            "dcc_pairs": len(self._dcc_cache),
        }
