from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import joblib
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "overseer_trades.db"
MODEL_PATH = ROOT / "ml" / "overseer_model.pkl"

SYMBOL_MAP = {"6EM6": 0, "6BM6": 1, "6AM6": 2, "6CM6": 3, "6JM6": 4}

OOS_START_ID = 35761

FW_NAMES = [
    "FW01_multi_tf_trend", "FW02_price_action", "FW03_volume",
    "FW04_liquidity_sweep", "FW05_weekly_levels", "FW06_session_kz",
    "FW07_econ_event", "FW08_asian_range", "FW09_cot_positioning",
    "FW10_post_news", "FW11_iv_skew", "FW12_dxy_isolation",
    "FW13_lag_arb", "FW14_risk_regime", "FW15_l3_flow",
    "FW16_directional_momentum", "FW17_volume_profile",
    "FW18_technical", "FW19_fundamental",
]


def row_to_features(row: dict) -> dict:
    fw = json.loads(row["framework_scores_json"]) if row["framework_scores_json"] else {}
    l3 = json.loads(row["l3_features_json"]) if row["l3_features_json"] else {}
    bias = json.loads(row["bias_breakdown_json"]) if row["bias_breakdown_json"] else {}
    sym = row["symbol"]
    direction = row["direction"]

    feat = {name: fw.get(name, 0.0) for name in FW_NAMES}
    feat["symbol_enc"] = SYMBOL_MAP.get(sym, -1)
    feat["is_buy"] = 1 if direction == "BUY" else 0
    feat["is_gbp"] = 1 if "6B" in sym else 0
    feat["is_aud"] = 1 if "6A" in sym else 0
    feat["is_eur"] = 1 if "6E" in sym else 0
    feat["is_jpy"] = 1 if "6J" in sym else 0
    feat["is_cad"] = 1 if "6C" in sym else 0
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
    return feat


def main():
    pipeline = joblib.load(MODEL_PATH)
    estimator = pipeline.named_steps["xgb"]
    feature_order = list(estimator.feature_names_in_)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT id, symbol, direction, score, adjusted_score,
               framework_scores_json, l3_features_json, bias_breakdown_json,
               spread_bps, risk_regime, session, dxy,
               outcome_200ticks
        FROM signal_log
        WHERE id >= ? AND outcome_200ticks IS NOT NULL AND outcome_200ticks != 'FLAT'
        ORDER BY id
    """, (OOS_START_ID,)).fetchall()

    print(f"OOS signals (id>={OOS_START_ID}): {len(rows)}")

    features = []
    labels = []
    symbols = []
    directions = []
    ids = []

    for r in rows:
        d = dict(r)
        feat = row_to_features(d)
        features.append(feat)
        labels.append(1 if d["outcome_200ticks"] == "WIN" else 0)
        symbols.append(d["symbol"])
        directions.append(d["direction"])
        ids.append(d["id"])

    df = pd.DataFrame(features)
    df = df.reindex(columns=feature_order, fill_value=0.0)
    preds = pipeline.predict_proba(df)[:, 1]

    print("\n=== OOS Win Rate by Threshold (ALL signals) ===")
    for thr in [0.70, 0.75, 0.80, 0.85, 0.90, 0.95]:
        mask = preds >= thr
        if mask.sum() > 0:
            wr = np.array(labels)[mask].mean() * 100
            wins = np.array(labels)[mask].sum()
            n = mask.sum()
            print(f"  >= {thr:.2f}: n={n} W={wins} L={n-wins} WR={wr:.1f}%")

    print("\n=== OOS Win Rate by Symbol+Direction at threshold 0.85 ===")
    for sym in ["6BM6", "6AM6", "6EM6", "6JM6", "6CM6"]:
        for d in ["BUY", "SELL"]:
            mask = (np.array(symbols) == sym) & (np.array(directions) == d) & (preds >= 0.85)
            if mask.sum() >= 3:
                wr = np.array(labels)[mask].mean() * 100
                wins = int(np.array(labels)[mask].sum())
                n = int(mask.sum())
                print(f"  {sym} {d}: n={n} W={wins} L={n-wins} WR={wr:.1f}%")

    print("\n=== OOS Win Rate by Symbol+Direction at threshold 0.90 ===")
    for sym in ["6BM6", "6AM6", "6EM6", "6JM6", "6CM6"]:
        for d in ["BUY", "SELL"]:
            mask = (np.array(symbols) == sym) & (np.array(directions) == d) & (preds >= 0.90)
            if mask.sum() >= 2:
                wr = np.array(labels)[mask].mean() * 100
                wins = int(np.array(labels)[mask].sum())
                n = int(mask.sum())
                print(f"  {sym} {d}: n={n} W={wins} L={n-wins} WR={wr:.1f}%")

    print("\n=== Best per-threshold for 90%+ target ===")
    for thr in [0.80, 0.85, 0.90, 0.95]:
        mask = preds >= thr
        if mask.sum() < 5:
            continue
        sub_labels = np.array(labels)[mask]
        sub_syms = np.array(symbols)[mask]
        sub_dirs = np.array(directions)[mask]
        best_wr = 0
        best_combo = ""
        best_n = 0
        for sym in set(sub_syms):
            for d in set(sub_dirs):
                m = (sub_syms == sym) & (sub_dirs == d)
                if m.sum() >= 5:
                    wr = sub_labels[m].mean() * 100
                    if wr > best_wr:
                        best_wr = wr
                        best_combo = f"{sym} {d}"
                        best_n = int(m.sum())
        print(f"  >= {thr:.2f}: best={best_combo} n={best_n} WR={best_wr:.1f}%")

    conn.close()


if __name__ == "__main__":
    main()
