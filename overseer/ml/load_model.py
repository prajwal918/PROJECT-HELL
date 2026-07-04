from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd

from ml.framework_scorer import aggregate_framework_scores, get_framework_feature_names

ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / "overseer_model.pkl"
WEIGHTS_PATH = ROOT / "gate_weights.json"
THRESHOLD = 0.90

_model = None
_weights: dict[str, float] = {}
_model_expects_extra: list[str] = []
_model_load_failed = False

SYMBOL_MAP = {"6EM6": 0, "6BM6": 1, "6AM6": 2, "6CM6": 3, "6JM6": 4}


def reload_model() -> None:
    global _model, _weights, _model_expects_extra, _model_load_failed
    _model = None
    _weights = {}
    _model_expects_extra = []
    _model_load_failed = False
    _load_artifacts()


def _load_artifacts() -> None:
    global _model, _weights, _model_expects_extra, _model_load_failed
    if _model is None and not _model_load_failed and MODEL_PATH.exists():
        try:
            _model = joblib.load(MODEL_PATH)
        except Exception as exc:
            import logging
            logging.getLogger("overseer.load_model").warning(
                "Model load failed (numpy compat?): %s — using weighted fallback", exc
            )
            _model = None
            _model_load_failed = True
    if _model is not None:
        estimator = _model
        if isinstance(_model, dict) and "model" in _model:
            estimator = _model["model"]
        elif hasattr(_model, "named_steps") and "xgb" in _model.named_steps:
            estimator = _model.named_steps["xgb"]
        if hasattr(estimator, "feature_names_in_"):
            all_feats = list(estimator.feature_names_in_)
            fw_set = set(get_framework_feature_names())
            _model_expects_extra = [f for f in all_feats if f not in fw_set]
    if not _weights and WEIGHTS_PATH.exists():
        _weights = json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))


def predict_trade_quality(gate_states_dict: dict[str, bool], tick: dict | None = None) -> float:
    _load_artifacts()
    fw_scores = aggregate_framework_scores(gate_states_dict)
    fw_names = get_framework_feature_names()
    row = {name: fw_scores.get(name, 0.0) for name in fw_names}

    if _model is not None and _model_expects_extra:
        sym = (tick or {}).get("symbol", "")
        direction = (tick or {}).get("direction", "")
        l3 = (tick or {}).get("_l3_features", {}) or {}
        bias = (tick or {}).get("_bias_breakdown", {}) or {}

        row["symbol_enc"] = SYMBOL_MAP.get(sym, -1)
        row["is_buy"] = 1 if direction == "BUY" else 0
        row["is_gbp"] = 1 if "6B" in sym else 0
        row["is_aud"] = 1 if "6A" in sym else 0
        row["is_eur"] = 1 if "6E" in sym else 0
        row["is_jpy"] = 1 if "6J" in sym else 0
        row["is_cad"] = 1 if "6C" in sym else 0
        row["spread_bps"] = float(tick.get("spread_bps", 0) or 0) if tick else 0
        row["dxy"] = float(tick.get("dxy", 0) or 0) if tick else 0
        row["risk_on"] = 1 if (tick or {}).get("risk_regime", "") == "risk_on" else 0
        row["risk_off"] = 1 if (tick or {}).get("risk_regime", "") == "risk_off" else 0
        row["l3_spoof"] = float(l3.get("spoof_reversal_signal", l3.get("spoof_signal", 0)))
        row["l3_queue"] = float(l3.get("queue_exhaustion_signal", l3.get("queue_exhaustion", 0)))
        row["l3_iceberg"] = float(l3.get("iceberg_detected", l3.get("iceberg_signal", 0)))
        row["l3_adverse"] = float(l3.get("adverse_selection_risk", l3.get("adverse_risk", 0)))
        row["l3_hft"] = float(l3.get("hft_cluster_detected", l3.get("hft_signal", 0)))
        row["l3_vacuum"] = float(l3.get("liquidity_vacuum_signal", l3.get("vacuum_signal", 0)))
        row["l3_pred"] = float(l3.get("l3_prediction", 0))
        row["l3_conf"] = float(l3.get("l3_confidence", 0))
        row["bias_spoof"] = float(bias.get("spoof_bias", 0))
        row["bias_queue"] = float(bias.get("queue_bias", 0))
        row["bias_iceberg"] = float(bias.get("iceberg_bias", 0))
        row["bias_adverse"] = float(bias.get("adverse_bias", 0))
        row["bias_hft"] = float(bias.get("hft_bias", 0))
        row["bias_vacuum"] = float(bias.get("vacuum_bias", 0))
        row["bias_iv"] = float(bias.get("iv_skew_bias", 0))
        row["bias_fundamental"] = float(bias.get("fundamental_bias", 0))
        row["bias_crowding"] = float(bias.get("bias_crowding", 0))

        session = (tick or {}).get("session", "") or ""
        row["session_asian"] = 1 if "asian" in session.lower() else 0
        row["session_london"] = 1 if "london" in session.lower() else 0
        row["session_ny"] = 1 if "ny" in session.lower() else 0
        row["session_overlap"] = 1 if "overlap" in session.lower() else 0

        row["gate_Z15"] = int(gate_states_dict.get("gate_Z15", False)) if gate_states_dict else 0
        row["gate_A"] = int(gate_states_dict.get("gate_A", False)) if gate_states_dict else 0
        row["gate_D"] = int(gate_states_dict.get("gate_D", False)) if gate_states_dict else 0
        row["gate_stacked_imbalance"] = int(gate_states_dict.get("gate_stacked_imbalance", False)) if gate_states_dict else 0
        row["gate_CVD"] = int(gate_states_dict.get("gate_CVD", False)) if gate_states_dict else 0
        row["gate_iceberg_monitor"] = int(gate_states_dict.get("gate_iceberg_monitor", False)) if gate_states_dict else 0
        row["gate_tape_velocity"] = int(gate_states_dict.get("gate_tape_velocity", False)) if gate_states_dict else 0
        row["gate_bar_cot"] = int(gate_states_dict.get("gate_bar_cot", False)) if gate_states_dict else 0
        row["gate_unfinished"] = int(gate_states_dict.get("gate_unfinished", False)) if gate_states_dict else 0
        row["gate_FVG"] = int(gate_states_dict.get("gate_FVG", False)) if gate_states_dict else 0
        row["gate_ORDER_BLOCK"] = int(gate_states_dict.get("gate_ORDER_BLOCK", False)) if gate_states_dict else 0
        row["gate_SFP"] = int(gate_states_dict.get("gate_SFP", False)) if gate_states_dict else 0
        row["gate_WYCKOFF"] = int(gate_states_dict.get("gate_WYCKOFF", False)) if gate_states_dict else 0
        row["gate_PO3"] = int(gate_states_dict.get("gate_PO3", False)) if gate_states_dict else 0
        row["gate_legendary_composite"] = int(gate_states_dict.get("gate_legendary_composite", False)) if gate_states_dict else 0
        row["gate_HURST"] = int(gate_states_dict.get("gate_HURST", False)) if gate_states_dict else 0
        row["gate_CURRENCY_STR"] = int(gate_states_dict.get("gate_CURRENCY_STR", False)) if gate_states_dict else 0
        row["gate_LONDON_FIX"] = int(gate_states_dict.get("gate_LONDON_FIX", False)) if gate_states_dict else 0
        row["gate_DXY_TREND"] = int(gate_states_dict.get("gate_DXY_TREND", False)) if gate_states_dict else 0
        row["gate_RETAIL_SENTIMENT"] = int(gate_states_dict.get("gate_RETAIL_SENTIMENT", False)) if gate_states_dict else 0
        row["gate_GAMMA_EXPOSURE"] = int(gate_states_dict.get("gate_GAMMA_EXPOSURE", False)) if gate_states_dict else 0

    if _model is not None:
        frame = pd.DataFrame([row])
        estimator = _model
        if isinstance(_model, dict) and "model" in _model:
            estimator = _model["model"]
        elif hasattr(_model, "named_steps") and "xgb" in _model.named_steps:
            estimator = _model.named_steps["xgb"]
        if hasattr(estimator, "feature_names_in_"):
            frame = frame.reindex(columns=list(estimator.feature_names_in_), fill_value=0.0)
        return float(estimator.predict_proba(frame)[0][1])

    if _weights:
        active_weight = sum(_weights.get(fw, 0.0) * row.get(fw, 0.0) for fw in fw_names)
        total_weight = sum(abs(w) for w in _weights.values()) or 1.0
        return max(0.0, min(1.0, active_weight / total_weight))

    return sum(row.values()) / len(row) if row else 0.0


def should_trade(gate_states_dict: dict[str, bool], tick: dict | None = None) -> bool:
    return predict_trade_quality(gate_states_dict, tick) > THRESHOLD
