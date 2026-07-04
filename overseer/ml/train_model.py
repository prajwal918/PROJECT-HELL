from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold, cross_val_score
from xgboost import XGBClassifier
from imblearn.pipeline import Pipeline as ImbPipeline
from imblearn.over_sampling import SMOTE

from ml.framework_scorer import get_framework_feature_names

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "overseer_trades.db"
MODEL_PATH = Path(__file__).resolve().parent / "overseer_model.pkl"
WEIGHTS_PATH = Path(__file__).resolve().parent / "gate_weights.json"

FW_NAMES = get_framework_feature_names()

SYMBOL_MAP = {"6EM6": 0, "6BM6": 1, "6AM6": 2, "6CM6": 3, "6JM6": 4}
SESSION_MAP = {"asian": 0, "london": 1, "ny": 2, "overlap": 3, "off": 4}
REGIME_MAP = {"risk_on": 0, "risk_off": 1, "neutral": 2}


def load_signal_outcomes() -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as conn:
        frame = pd.read_sql_query(
            """
            SELECT id, symbol, direction, score, adjusted_score,
            gate_states_json, framework_scores_json,
            l3_features_json, bias_breakdown_json,
            spread_bps, risk_regime, session, dxy,
            outcome_200ticks, timestamp
            FROM signal_log
            WHERE outcome_200ticks IS NOT NULL
            AND outcome_200ticks != 'FLAT'
            ORDER BY timestamp ASC
            """,
            conn,
        )
    if frame.empty:
        raise RuntimeError("No non-FLAT signal outcomes available for training.")
    return frame


def extract_features(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in frame.iterrows():
        fw = json.loads(row["framework_scores_json"]) if row["framework_scores_json"] else {}
        l3 = json.loads(row["l3_features_json"]) if row["l3_features_json"] else {}
        bias = json.loads(row["bias_breakdown_json"]) if row["bias_breakdown_json"] else {}

        feat = {name: fw.get(name, 0.0) for name in FW_NAMES}
        feat["symbol_enc"] = SYMBOL_MAP.get(row["symbol"], -1)
        feat["is_buy"] = 1 if row["direction"] == "BUY" else 0
        feat["is_gbp"] = 1 if "6B" in row["symbol"] else 0
        feat["is_aud"] = 1 if "6A" in row["symbol"] else 0
        feat["is_eur"] = 1 if "6E" in row["symbol"] else 0
        feat["is_jpy"] = 1 if "6J" in row["symbol"] else 0
        feat["is_cad"] = 1 if "6C" in row["symbol"] else 0
        feat["spread_bps"] = float(row.get("spread_bps", 0) or 0)
        feat["dxy"] = float(row.get("dxy", 0) or 0)
        feat["risk_on"] = 1 if row.get("risk_regime", "") == "risk_on" else 0
        feat["risk_off"] = 1 if row.get("risk_regime", "") == "risk_off" else 0
        feat["session_asian"] = 1 if row.get("session", "") == "asian" else 0
        feat["session_london"] = 1 if row.get("session", "") == "london" else 0
        feat["session_ny"] = 1 if row.get("session", "") == "ny" else 0
        feat["session_overlap"] = 1 if row.get("session", "") == "overlap" else 0
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
        feat["bias_crowding"] = float(bias.get("bias_crowding", 0))

        gates = json.loads(row["gate_states_json"]) if row.get("gate_states_json") else {}
        feat["gate_Z15"] = int(gates.get("gate_Z15", False))
        feat["gate_A"] = int(gates.get("gate_A", False))
        feat["gate_D"] = int(gates.get("gate_D", False))
        feat["gate_stacked_imbalance"] = int(gates.get("gate_stacked_imbalance", False))
        feat["gate_CVD"] = int(gates.get("gate_CVD", False))
        feat["gate_iceberg_monitor"] = int(gates.get("gate_iceberg_monitor", False))
        feat["gate_tape_velocity"] = int(gates.get("gate_tape_velocity", False))
        feat["gate_bar_cot"] = int(gates.get("gate_bar_cot", False))
        feat["gate_unfinished"] = int(gates.get("gate_unfinished", False))
        feat["gate_FVG"] = int(gates.get("gate_FVG", False))
        feat["gate_ORDER_BLOCK"] = int(gates.get("gate_ORDER_BLOCK", False))
        feat["gate_SFP"] = int(gates.get("gate_SFP", False))
        feat["gate_WYCKOFF"] = int(gates.get("gate_WYCKOFF", False))
        feat["gate_PO3"] = int(gates.get("gate_PO3", False))
        feat["gate_legendary_composite"] = int(gates.get("gate_legendary_composite", False))
        feat["gate_HURST"] = int(gates.get("gate_HURST", False))
        feat["gate_CURRENCY_STR"] = int(gates.get("gate_CURRENCY_STR", False))
        feat["gate_LONDON_FIX"] = int(gates.get("gate_LONDON_FIX", False))
        feat["gate_DXY_TREND"] = int(gates.get("gate_DXY_TREND", False))
        feat["gate_RETAIL_SENTIMENT"] = int(gates.get("gate_RETAIL_SENTIMENT", False))
        feat["gate_GAMMA_EXPOSURE"] = int(gates.get("gate_GAMMA_EXPOSURE", False))

        rows.append(feat)
    return pd.DataFrame(rows)


def train() -> None:
    frame = load_signal_outcomes()
    print(f"Loaded {len(frame)} non-FLAT signal outcomes")

    x = extract_features(frame)
    y = (frame["outcome_200ticks"] == "WIN").astype(int)

    win_count = int(y.sum())
    loss_count = int((1 - y).sum())
    print(f"WIN={win_count} LOSS={loss_count} WR={win_count/(win_count+loss_count)*100:.1f}%")

    if y.nunique() < 2:
        raise RuntimeError("Training target has one class only.")

    # --- Per-symbol-direction sample weights to prevent majority pair domination ---
    pair_counts = frame.groupby(["symbol", "direction"]).size()
    max_count = pair_counts.max()
    sample_weights = np.ones(len(frame))
    for i, (_, row) in enumerate(frame.iterrows()):
        key = (row["symbol"], row["direction"])
        count = pair_counts.get(key, 1)
        sample_weights[i] = max_count / count
    print(f"Sample weight range: {sample_weights.min():.2f} - {sample_weights.max():.2f}")

    # --- OOS Split: last 20% of data (time-ordered) ---
    split_idx = int(len(frame) * 0.8)
    x_train, x_oos = x.iloc[:split_idx], x.iloc[split_idx:]
    y_train, y_oos = y.iloc[:split_idx], y.iloc[split_idx:]
    sw_train = sample_weights[:split_idx]
    frame_train, frame_oos = frame.iloc[:split_idx], frame.iloc[split_idx:]
    print(f"Train: {len(x_train)} OOS: {len(x_oos)}")

    minority_count = int(y_train.value_counts().min())
    k_neighbors = max(1, min(5, minority_count - 1)) if minority_count >= 2 else 1

    xgb = XGBClassifier(
        n_estimators=500,
        max_depth=4,
        learning_rate=0.03,
        subsample=0.7,
        colsample_bytree=0.6,
        min_child_weight=10,
        gamma=1.0,
        reg_alpha=1.0,
        reg_lambda=5.0,
        scale_pos_weight=max(1, loss_count / max(win_count, 1)),
        use_label_encoder=False,
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
    )

    # SMOTE on training data, then apply sample weights to XGB fit
    smote = SMOTE(k_neighbors=k_neighbors, random_state=42)
    x_res, y_res = smote.fit_resample(x_train, y_train)
    # After SMOTE, rebuild sample weights for resampled data
    # Original samples keep their weights; synthetic samples get average weight
    n_orig = len(x_train)
    n_syn = len(x_res) - n_orig
    orig_weights = sw_train
    avg_weight = np.mean(orig_weights) if len(orig_weights) > 0 else 1.0
    syn_weights = np.full(n_syn, avg_weight)
    sw_res = np.concatenate([orig_weights, syn_weights])

    xgb.fit(x_res, y_res, sample_weight=sw_res)

    pipeline = ImbPipeline([
        ("smote", SMOTE(k_neighbors=k_neighbors, random_state=42)),
        ("xgb", XGBClassifier(
            n_estimators=500,
            max_depth=4,
            learning_rate=0.03,
            subsample=0.7,
            colsample_bytree=0.6,
            min_child_weight=10,
            gamma=1.0,
            reg_alpha=1.0,
            reg_lambda=5.0,
            scale_pos_weight=max(1, loss_count / max(win_count, 1)),
            use_label_encoder=False,
            eval_metric="logloss",
            random_state=42,
            n_jobs=-1,
        )),
    ])

    splits = min(5, minority_count)
    if splits >= 2:
        cv = StratifiedKFold(n_splits=splits, shuffle=True, random_state=42)
        scores = cross_val_score(pipeline, x_train, y_train, cv=cv, scoring="roc_auc")
        print(f"CV ROC AUC: mean={scores.mean():.4f} std={scores.std():.4f}")
    else:
        print("CV skipped.")

    # Save the weighted model (not the pipeline — pipeline doesn't support sample_weight)
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": xgb, "smote": smote, "feature_names": list(x.columns)}, MODEL_PATH)

    model = xgb
    importances = pd.Series(model.feature_importances_, index=x.columns).sort_values(ascending=False)
    print("\nFeature importances (top 20):")
    for feat, imp in importances.head(20).items():
        print(f" {feat}: {imp:.6f}")

    weights = {fw: round(float(imp), 6) for fw, imp in importances.items()}
    WEIGHTS_PATH.write_text(json.dumps(weights, indent=2, sort_keys=True), encoding="utf-8")

    # --- OOS Validation ---
    oos_proba = xgb.predict_proba(x_oos)[:, 1]
    x_oos_copy = x_oos.copy()
    x_oos_copy["pred_prob"] = oos_proba
    x_oos_copy["actual"] = y_oos.values
    x_oos_copy["symbol"] = frame_oos["symbol"].values
    x_oos_copy["direction"] = frame_oos["direction"].values

    try:
        from sklearn.metrics import roc_auc_score
        oos_auc = roc_auc_score(y_oos, oos_proba)
        print(f"\nOOS ROC AUC: {oos_auc:.4f}")
    except Exception:
        print("\nOOS AUC: could not compute")

    print("\nOOS threshold analysis:")
    for thr in [0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95]:
        mask = x_oos_copy["pred_prob"] >= thr
        if mask.sum() > 0:
            sub_wr = x_oos_copy.loc[mask, "actual"].mean() * 100
            print(f" All signals >= {thr:.2f}: n={mask.sum()} WR={sub_wr:.1f}%")

    print("\nOOS per-symbol-direction at threshold 0.80:")
    for sym in ["6BM6", "6AM6", "6EM6", "6JM6", "6CM6"]:
        for d in ["BUY", "SELL"]:
            mask = (x_oos_copy["pred_prob"] >= 0.80) & (x_oos_copy["symbol"] == sym) & (x_oos_copy["direction"] == d)
            if mask.sum() >= 3:
                sub_wr = x_oos_copy.loc[mask, "actual"].mean() * 100
                print(f" {sym} {d}: n={mask.sum()} WR={sub_wr:.1f}%")

    # Also show in-sample for comparison
    x_is = x_train.copy()
    x_is["pred_prob"] = xgb.predict_proba(x_train)[:, 1]
    x_is["actual"] = y_train.values
    print("\nIn-sample threshold analysis:")
    for thr in [0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95]:
        mask = x_is["pred_prob"] >= thr
        if mask.sum() > 0:
            sub_wr = x_is.loc[mask, "actual"].mean() * 100
            print(f" All signals >= {thr:.2f}: n={mask.sum()} WR={sub_wr:.1f}%")

    print(f"\nSaved model: {MODEL_PATH}")


if __name__ == "__main__":
    train()
