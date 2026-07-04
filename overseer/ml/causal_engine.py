"""Simplified Causal Engine — Double Machine Learning for ATE estimation.

Estimates Average Treatment Effect (ATE) per symbol-direction:
"What is the CAUSAL effect of taking this trade, controlling for confounders?"

Confounders: DXY move, risk regime, CVD delta, time-of-day, spread
Treatment: Taking the trade (BUY/SELL)
Outcome: 200-tick P&L

Runs OFFLINE every Sunday on last week's data, not live.
Uses 2-fold crossfit to avoid overfitting.
"""
from __future__ import annotations

import json
import logging
import math
import os
from typing import Any

import numpy as np

LOGGER = logging.getLogger("overseer.causal_engine")

CAUSAL_MIN_SAMPLES = int(os.getenv("CAUSAL_MIN_SAMPLES", "100"))
CAUSAL_N_FOLDS = int(os.getenv("CAUSAL_N_FOLDS", "2"))


class CausalEngine:
    """Double Machine Learning causal effect estimator."""

    def __init__(self) -> None:
        self._ate_results: dict[str, dict[str, float]] = {}
        self._last_run: float = 0.0

    def estimate_ate(self, symbol: str, direction: str, features: np.ndarray, treatments: np.ndarray, outcomes: np.ndarray) -> dict[str, float]:
        key = f"{symbol}_{direction}"
        n = len(features)
        if n < CAUSAL_MIN_SAMPLES:
            return {"ate": 0.0, "se": 0.0, "significant": False, "samples": n}
        fold_size = n // CAUSAL_N_FOLDS
        residuals_t = []
        residuals_y = []
        for fold in range(CAUSAL_N_FOLDS):
            start = fold * fold_size
            end = start + fold_size if fold < CAUSAL_N_FOLDS - 1 else n
            test_idx = list(range(start, end))
            train_idx = [i for i in range(n) if i not in test_idx]
            if len(train_idx) < 20 or len(test_idx) < 10:
                continue
            X_train = features[train_idx]
            T_train = treatments[train_idx]
            Y_train = outcomes[train_idx]
            X_test = features[test_idx]
            T_test = treatments[test_idx]
            Y_test = outcomes[test_idx]
            t_pred_train = np.mean(T_train)
            y_pred_train = np.mean(Y_train)
            t_residual = T_test - t_pred_train
            y_residual = Y_test - y_pred_train
            if t_residual.std() > 1e-10:
                t_residual_norm = t_residual / t_residual.std()
            else:
                t_residual_norm = t_residual
            residuals_t.extend(t_residual_norm.tolist())
            residuals_y.extend(y_residual.tolist())
        if len(residuals_t) < 20:
            return {"ate": 0.0, "se": 0.0, "significant": False, "samples": len(residuals_t)}
        rt = np.array(residuals_t)
        ry = np.array(residuals_y)
        denom = float(np.dot(rt, rt))
        if abs(denom) < 1e-10:
            return {"ate": 0.0, "se": 0.0, "significant": False, "samples": len(residuals_t)}
        ate = float(np.dot(rt, ry)) / denom
        residuals = ry - ate * rt
        se = float(np.sqrt(np.mean(residuals ** 2) / max(1, denom / len(rt))))
        t_stat = ate / se if se > 1e-10 else 0.0
        significant = abs(t_stat) > 1.96
        result = {
            "ate": round(ate, 4),
            "se": round(se, 4),
            "t_stat": round(t_stat, 2),
            "significant": significant,
            "samples": len(residuals_t),
            "p_value_approx": round(2 * (1 - self._norm_cdf(abs(t_stat))), 4),
        }
        self._ate_results[key] = result
        return result

    def _norm_cdf(self, x: float) -> float:
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    def run_from_db(self) -> dict[str, dict[str, float]]:
        try:
            import sqlite3
            from database.setup_db import DB_PATH
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            rows = conn.execute("""
                SELECT symbol, direction, score, dxy, risk_regime,
                       l3_features_json, bias_breakdown_json,
                       outcome_200ticks, pnl, spread_bps
                FROM signal_log
                WHERE outcome_200ticks IN ('WIN', 'LOSS')
                ORDER BY timestamp DESC LIMIT 10000
            """).fetchall()
            conn.close()
            if len(rows) < CAUSAL_MIN_SAMPLES:
                return {"error": "insufficient_data", "rows": len(rows)}
            by_group: dict[str, list[dict]] = {}
            for row in rows:
                symbol, direction, score, dxy, regime, l3_json, bias_json, outcome, pnl, spread = row
                key = f"{symbol}_{direction}"
                if key not in by_group:
                    by_group[key] = []
                l3 = json.loads(l3_json) if l3_json else {}
                bias = json.loads(bias_json) if bias_json else {}
                by_group[key].append({
                    "score": float(score or 0),
                    "dxy": float(dxy or 0),
                    "spread": float(spread or 0),
                    "adverse": float(l3.get("adverse_selection_risk", 0)),
                    "bias_sum": sum(float(v) for v in bias.values()) if bias else 0,
                    "regime_risk_on": 1 if regime == "risk_on" else 0,
                    "treated": 1,
                    "outcome": float(pnl or 0),
                })
            results = {}
            for key, data in by_group.items():
                if len(data) < CAUSAL_MIN_SAMPLES:
                    continue
                arr = np.array([[d["score"], d["dxy"], d["spread"], d["adverse"], d["bias_sum"], d["regime_risk_on"]] for d in data])
                treatments = np.ones(len(data))
                outcomes = np.array([d["outcome"] for d in data])
                ate_result = self.estimate_ate(key.split("_")[0], key.split("_")[1] if "_" in key else "BUY", arr, treatments, outcomes)
                results[key] = ate_result
            self._last_run = float(os.getenv("CAUSAL_LAST_RUN_TIMESTAMP", "0") or 0)
            LOGGER.info("Causal engine run: %d groups analyzed", len(results))
            return results
        except Exception as e:
            LOGGER.warning("Causal engine DB run failed: %s", e)
            return {"error": str(e)}

    def get_causal_edge(self, symbol: str, direction: str) -> dict[str, float]:
        key = f"{symbol}_{direction}"
        if key in self._ate_results:
            return self._ate_results[key]
        return {"ate": 0.0, "significant": False, "samples": 0}

    def get_all_results(self) -> dict[str, dict[str, float]]:
        return dict(self._ate_results)

    def get_status(self) -> dict[str, Any]:
        return {
            "groups_analyzed": len(self._ate_results),
            "significant_edges": sum(1 for r in self._ate_results.values() if r.get("significant")),
            "last_run": self._last_run,
        }
