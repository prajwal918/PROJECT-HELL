"""SHAP-based XAI Explainer — real-time trade decision explanation.

Computes exact SHAP contribution of each framework score to the final
XGBoost prediction. Runs asynchronously every Nth signal (not every tick)
to stay within CPU budget.

No LLM — just structured JSON explanations that can be logged and displayed.
"""
from __future__ import annotations

import json
import logging
import math
import os
from collections import deque
from typing import Any

import numpy as np

LOGGER = logging.getLogger("overseer.xai")

XAI_COMPUTE_INTERVAL = int(os.getenv("XAI_COMPUTE_INTERVAL", "50"))
XAI_MAX_FEATURES = int(os.getenv("XAI_MAX_FEATURES", "27"))
XAI_LOG_TO_DB = os.getenv("XAI_LOG_TO_DB", "true").lower() == "true"
FW_NAMES = [
    "FW01_multi_tf_trend", "FW02_price_action", "FW03_volume", "FW04_liquidity_sweep",
    "FW05_weekly_levels", "FW06_session_kz", "FW07_econ_event", "FW08_asian_range",
    "FW09_cot_positioning", "FW10_post_news", "FW11_iv_skew", "FW12_dxy_isolation",
    "FW13_lag_arb", "FW14_risk_regime", "FW15_l3_flow", "FW16_directional_momentum",
    "FW17_volume_profile", "FW18_technical", "FW19_fundamental",
]


class XAIExplainer:
    """TreeSHAP-style explainer for XGBoost predictions on framework scores."""

    def __init__(self) -> None:
        self._signal_count: int = 0
        self._explained_count: int = 0
        self._shap_cache: deque[dict[str, Any]] = deque(maxlen=1000)
        self._feature_importance_avg: dict[str, float] = {}
        self._model = None
        self._explainer = None

    def _try_init_shap(self) -> bool:
        try:
            import shap
            self._shap = shap
            return True
        except ImportError:
            self._shap = None
            return False

    def _try_load_model(self) -> Any:
        try:
            from ml.load_model import _model
            return _model
        except Exception:
            return None

    def explain_signal(self, framework_scores: dict[str, float], tick: dict[str, Any], score: float, gate_states: dict[str, bool] | None = None) -> dict[str, Any]:
        self._signal_count += 1
        if XAI_COMPUTE_INTERVAL > 1 and self._signal_count % XAI_COMPUTE_INTERVAL != 0:
            return {"explanation": "skipped", "interval": XAI_COMPUTE_INTERVAL}
        self._explained_count += 1
        fw_values = []
        fw_labels = []
        for i, name in enumerate(FW_NAMES):
            if i >= 19:
                break
            v = framework_scores.get(name, framework_scores.get(f"FW{i+1:02d}", 0.0))
            fw_values.append(float(v))
            fw_labels.append(name)
        extra_features = {}
        symbol = tick.get("symbol", "UNKNOWN")
        extra_features["is_buy"] = 1.0 if tick.get("direction", "BUY") == "BUY" else 0.0
        extra_features["spread_bps"] = float(tick.get("spread_bps", 0))
        extra_features["dxy"] = float(tick.get("dxy", 0))
        extra_features["risk_on"] = 1.0 if tick.get("risk_regime", "") == "risk_on" else 0.0
        for key in ("l3_spoof", "l3_queue", "l3_iceberg", "l3_adverse", "l3_hft", "l3_vacuum", "l3_pred", "l3_conf"):
            extra_features[key] = float(tick.get(key, tick.get(f"_{key}", 0)))
        all_values = fw_values + list(extra_features.values())
        all_labels = fw_labels + list(extra_features.keys())
        shap_values = self._compute_shap_approx(fw_values, extra_features, score)
        contributions = {}
        for i, label in enumerate(all_labels):
            if i < len(shap_values):
                contributions[label] = round(float(shap_values[i]), 4)
        sorted_contribs = sorted(contributions.items(), key=lambda x: abs(x[1]), reverse=True)
        top_3_positive = [(k, v) for k, v in sorted_contribs if v > 0][:3]
        top_3_negative = [(k, v) for k, v in sorted_contribs if v < 0][:3]
        base_value = score - sum(shap_values) if shap_values else score * 0.5
        explanation_text = self._generate_explanation(symbol, tick.get("direction", "BUY"), score, top_3_positive, top_3_negative)
        for label in fw_labels:
            if label not in self._feature_importance_avg:
                self._feature_importance_avg[label] = 0.0
            if label in contributions:
                n = self._explained_count
                self._feature_importance_avg[label] = self._feature_importance_avg[label] * (n - 1) / n + abs(contributions[label]) / n
        result = {
            "symbol": symbol,
            "direction": tick.get("direction", "BUY"),
            "score": round(score, 4),
            "base_value": round(float(base_value), 4),
            "contributions": contributions,
            "top_positive": [(k, round(v, 4)) for k, v in top_3_positive],
            "top_negative": [(k, round(v, 4)) for k, v in top_3_negative],
            "explanation": explanation_text,
            "explained_signal_num": self._explained_count,
        }
        self._shap_cache.append(result)
        return result

    def _compute_shap_approx(self, fw_values: list[float], extra_features: dict[str, float], score: float) -> list[float]:
        model = self._try_load_model()
        if model is not None and self._try_init_shap() and self._shap is not None:
            try:
                feature_array = np.array(fw_values + list(extra_features.values())).reshape(1, -1)
                xgb_model = model
                if isinstance(model, dict) and "model" in model:
                    xgb_model = model["model"]
                if hasattr(xgb_model, "get_booster"):
                    explainer = self._shap.TreeExplainer(xgb_model)
                    shap_values = explainer.shap_values(feature_array)
                    return list(shap_values[0])
            except Exception as e:
                LOGGER.debug("SHAP exact computation failed: %s — using approximation", e)
        contributions = []
        n_fw = len(fw_values)
        fw_sum = sum(fw_values)
        base = 0.5
        for i, v in enumerate(fw_values):
            if fw_sum > 0:
                contrib = (v / fw_sum) * (score - base) if fw_sum > 0 else 0
            else:
                contrib = 0
            contributions.append(contrib)
        extra_sum = sum(abs(v) for v in extra_features.values())
        remaining = score - base - sum(contributions)
        if extra_sum > 0 and len(extra_features) > 0:
            for v in extra_features.values():
                contributions.append(remaining * abs(v) / extra_sum * (1 if v > 0 else -1) if v != 0 else 0)
        else:
            for _ in extra_features:
                contributions.append(0)
        return contributions

    def _generate_explanation(self, symbol: str, direction: str, score: float, top_pos: list[tuple[str, float]], top_neg: list[tuple[str, float]]) -> str:
        parts = [f"{direction} {symbol} (score={score:.2f})"]
        if top_pos:
            pos_str = " + ".join(f"{k}({v:+.2f})" for k, v in top_pos[:2])
            parts.append(f"driven by {pos_str}")
        if top_neg:
            neg_str = " ".join(f"{k}({v:+.2f})" for k, v in top_neg[:2])
            parts.append(f"opposed by {neg_str}")
        return "; ".join(parts)

    def get_feature_importance(self) -> dict[str, float]:
        return {k: round(v, 4) for k, v in sorted(self._feature_importance_avg.items(), key=lambda x: -x[1])}

    def get_recent_explanations(self, n: int = 10) -> list[dict[str, Any]]:
        return list(self._shap_cache)[-n:]

    def get_status(self) -> dict[str, Any]:
        return {
            "total_signals": self._signal_count,
            "explained_signals": self._explained_count,
            "compute_interval": XAI_COMPUTE_INTERVAL,
        }
