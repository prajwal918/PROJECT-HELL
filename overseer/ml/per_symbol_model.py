from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import Pipeline as ImbPipeline
from sklearn.model_selection import StratifiedKFold, cross_val_score
from xgboost import XGBClassifier

from ml.framework_scorer import get_framework_feature_names
from ml.load_model import predict_trade_quality as global_predict

LOGGER = logging.getLogger("overseer.per_symbol_models")

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "overseer_trades.db"
MODEL_DIR = Path(__file__).resolve().parent / "per_symbol"

FW_NAMES = get_framework_feature_names()

SYMBOL_MAP = {"6EM6": 0, "6BM6": 1, "6AM6": 2, "6CM6": 3, "6JM6": 4}
MIN_SAMPLES_PER_SYMBOL = int(os.environ.get("PER_SYMBOL_MIN_SAMPLES", "100")) if (os := __import__("os")) else 100


def _symbol_model_path(symbol: str) -> Path:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    return MODEL_DIR / f"model_{symbol}.pkl"


def _extract_features_for_symbol(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in frame.iterrows():
        fw = json.loads(row["framework_scores_json"]) if row["framework_scores_json"] else {}
        l3 = json.loads(row["l3_features_json"]) if row["l3_features_json"] else {}
        bias = json.loads(row["bias_breakdown_json"]) if row["bias_breakdown_json"] else {}

        feat = {name: fw.get(name, 0.0) for name in FW_NAMES}
        feat["is_buy"] = 1 if row["direction"] == "BUY" else 0
        feat["spread_bps"] = float(row.get("spread_bps", 0) or 0)
        feat["dxy"] = float(row.get("dxy", 0) or 0)
        feat["risk_on"] = 1 if row.get("risk_regime", "") == "risk_on" else 0
        feat["risk_off"] = 1 if row.get("risk_regime", "") == "risk_off" else 0
        feat["l3_spoof"] = float(l3.get("spoof_reversal_signal", l3.get("spoof_signal", 0)))
        feat["l3_queue"] = float(l3.get("queue_exhaustion_signal", l3.get("queue_exhaustion", 0)))
        feat["l3_iceberg"] = float(l3.get("iceberg_detected", l3.get("iceberg_signal", 0)))
        feat["l3_adverse"] = float(l3.get("adverse_selection_risk", l3.get("adverse_risk", 0)))
        feat["l3_hft"] = float(l3.get("hft_cluster_detected", l3.get("hft_signal", 0)))
        feat["l3_vacuum"] = float(l3.get("liquidity_vacuum_signal", l3.get("vacuum_signal", 0)))
        feat["l3_pred"] = float(l3.get("l3_prediction", 0))
        feat["l3_conf"] = float(l3.get("l3_confidence", 0))
        feat["bias_spoof"] = float(bias.get("spoof_bias", 0))
        feat["bias_queue"] = float(bias.get("queue_bias", 0))
        feat["bias_iceberg"] = float(bias.get("iceberg_bias", 0))
        feat["bias_adverse"] = float(bias.get("adverse_bias", 0))
        feat["bias_hft"] = float(bias.get("hft_bias", 0))
        feat["bias_vacuum"] = float(bias.get("vacuum_bias", 0))
        feat["bias_iv"] = float(bias.get("iv_skew_bias", 0))
        feat["bias_fundamental"] = float(bias.get("fundamental_bias", bias.get("bias_fundamental", 0)))
        rows.append(feat)
    return pd.DataFrame(rows)


def train_per_symbol(symbol: str) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        frame = pd.read_sql_query(
            """
            SELECT id, symbol, direction, score, adjusted_score,
                   gate_states_json, framework_scores_json,
                   l3_features_json, bias_breakdown_json,
                   spread_bps, risk_regime, session, dxy,
                   outcome_200ticks
            FROM signal_log
            WHERE symbol = ? AND outcome_200ticks IS NOT NULL
            AND outcome_200ticks != 'FLAT'
            """,
            conn,
            params=(symbol,),
        )

    if len(frame) < MIN_SAMPLES_PER_SYMBOL:
        LOGGER.info("Skipping per-symbol model for %s: only %d samples (need %d)", symbol, len(frame), MIN_SAMPLES_PER_SYMBOL)
        return False

    x = _extract_features_for_symbol(frame)
    y = (frame["outcome_200ticks"] == "WIN").astype(int)

    if y.nunique() < 2:
        LOGGER.warning("Skipping per-symbol model for %s: single class", symbol)
        return False

    win_count = int(y.sum())
    loss_count = int((1 - y).sum())
    LOGGER.info("Training per-symbol model for %s: %d samples, WIN=%d LOSS=%d WR=%.1f%%",
                symbol, len(frame), win_count, loss_count, win_count / (win_count + loss_count) * 100)

    minority_count = int(y.value_counts().min())
    k_neighbors = max(1, min(5, minority_count - 1)) if minority_count >= 2 else 1

    pipeline = ImbPipeline([
        ("smote", SMOTE(k_neighbors=k_neighbors, random_state=42)),
        ("xgb", XGBClassifier(
            n_estimators=300,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.7,
            min_child_weight=5,
            gamma=0.5,
            reg_alpha=0.5,
            reg_lambda=3.0,
            scale_pos_weight=max(1, loss_count / max(win_count, 1)),
            use_label_encoder=False,
            eval_metric="logloss",
            random_state=42,
        )),
    ])

    splits = min(5, minority_count)
    if splits >= 2:
        cv = StratifiedKFold(n_splits=splits, shuffle=True, random_state=42)
        scores = cross_val_score(pipeline, x, y, cv=cv, scoring="roc_auc")
        LOGGER.info("Per-symbol %s CV AUC: mean=%.4f std=%.4f", symbol, scores.mean(), scores.std())

    pipeline.fit(x, y)
    model_path = _symbol_model_path(symbol)
    joblib.dump(pipeline, model_path)
    LOGGER.info("Saved per-symbol model: %s", model_path)
    return True


def train_all_per_symbol() -> dict[str, bool]:
    results = {}
    for symbol in ("6EM6", "6BM6", "6AM6", "6CM6", "6JM6"):
        results[symbol] = train_per_symbol(symbol)
    return results


class PerSymbolModelManager:
    def __init__(self) -> None:
        self._models: dict[str, Any] = {}
        self._load_available()

    def _load_available(self) -> None:
        for symbol in ("6EM6", "6BM6", "6AM6", "6CM6", "6JM6"):
            path = _symbol_model_path(symbol)
            if path.exists():
                try:
                    self._models[symbol] = joblib.load(path)
                    LOGGER.info("Loaded per-symbol model for %s", symbol)
                except Exception as exc:
                    LOGGER.error("Failed to load per-symbol model for %s: %s", symbol, exc)

    def predict(self, symbol: str, gate_states: dict[str, bool], tick: dict) -> float:
        model = self._models.get(symbol)
        if model is None:
            return global_predict(gate_states, tick)

        try:
            from ml.framework_scorer import aggregate_framework_scores
            fw_scores = aggregate_framework_scores(gate_states)
            row = {name: fw_scores.get(name, 0.0) for name in FW_NAMES}

            direction = tick.get("direction", "")
            l3 = tick.get("_l3_features", {}) or {}
            bias = tick.get("_bias_breakdown", {}) or {}

            row["is_buy"] = 1 if direction == "BUY" else 0
            row["spread_bps"] = float(tick.get("spread_bps", 0) or 0)
            row["dxy"] = float(tick.get("dxy", 0) or 0)
            row["risk_on"] = 1 if tick.get("risk_regime", "") == "risk_on" else 0
            row["risk_off"] = 1 if tick.get("risk_regime", "") == "risk_off" else 0
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

            frame = pd.DataFrame([row])
            estimator = model
            if hasattr(model, "named_steps") and "xgb" in model.named_steps:
                estimator = model.named_steps["xgb"]
            if hasattr(estimator, "feature_names_in_"):
                frame = frame.reindex(columns=list(estimator.feature_names_in_), fill_value=0.0)

            return float(model.predict_proba(frame)[0][1])
        except Exception as exc:
            LOGGER.error("Per-symbol model failed for %s, falling back to global: %s", symbol, exc)
            return global_predict(gate_states, tick)

    def has_model(self, symbol: str) -> bool:
        return symbol in self._models

    def reload(self) -> None:
        self._models.clear()
        self._load_available()

    def get_status(self) -> dict[str, Any]:
        return {
            "available_symbols": list(self._models.keys()),
            "missing_symbols": [s for s in ("6EM6", "6BM6", "6AM6", "6CM6", "6JM6") if s not in self._models],
        }
