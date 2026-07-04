import json, sqlite3, sys
import numpy as np
import joblib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.framework_scorer import get_framework_feature_names
from ml.train_model import SYMBOL_MAP, extract_features

DB = "database/overseer_trades.db"
MODEL = "ml/overseer_model.pkl"

pipeline = joblib.load(MODEL)
model = pipeline.named_steps["xgb"]
FW_NAMES = get_framework_feature_names()

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

oos_start = 35761
cur.execute("""SELECT id, symbol, direction, score, adjusted_score,
    gate_states_json, framework_scores_json,
    l3_features_json, bias_breakdown_json,
    spread_bps, risk_regime, session, dxy,
    outcome_200ticks
    FROM signal_log WHERE id >= ? AND outcome_200ticks IS NOT NULL AND outcome_200ticks != 'FLAT'
""", (oos_start,))

import pandas as pd
frame = pd.read_sql_query(
    """SELECT id, symbol, direction, score, adjusted_score,
    gate_states_json, framework_scores_json,
    l3_features_json, bias_breakdown_json,
    spread_bps, risk_regime, session, dxy,
    outcome_200ticks
    FROM signal_log WHERE id >= ? AND outcome_200ticks IS NOT NULL AND outcome_200ticks != 'FLAT'
    """, conn, params=(oos_start,)

)

x = extract_features(frame)
probs = pipeline.predict_proba(x)[:, 1]
y = (frame["outcome_200ticks"] == "WIN").astype(int)

print("=== NEW MODEL OOS PREDICTIONS ===")
print(f"Total OOS non-FLAT: {len(frame)}")

for thr in [0.80, 0.85, 0.90, 0.95]:
    mask = probs >= thr
    if mask.sum() > 0:
        wr = y[mask].mean() * 100
        print(f"  >= {thr}: n={mask.sum()} WR={wr:.1f}%")

print("\n=== PER SYMBOL+DIRECTION at >= 0.85 ===")
for sym in ["6BM6", "6AM6", "6CM6", "6JM6", "6EM6"]:
    for d in ["BUY", "SELL"]:
        mask = (probs >= 0.85) & (frame["symbol"] == sym) & (frame["direction"] == d)
        if mask.sum() >= 2:
            wr = y[mask].mean() * 100
            print(f"  {sym} {d}: n={mask.sum()} WR={wr:.1f}%")

print("\n=== PER SYMBOL+DIRECTION at >= 0.90 ===")
for sym in ["6BM6", "6AM6", "6CM6", "6JM6", "6EM6"]:
    for d in ["BUY", "SELL"]:
        mask = (probs >= 0.90) & (frame["symbol"] == sym) & (frame["direction"] == d)
        if mask.sum() >= 2:
            wr = y[mask].mean() * 100
            print(f"  {sym} {d}: n={mask.sum()} WR={wr:.1f}%")

conn.close()
