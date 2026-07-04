"""Backfill FW19_fundamental + bias_fundamental into existing signal_log entries."""
import json
import sqlite3
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from ml.fundamental_bias import get_fundamental_bias_adjustment

DB_PATH = str(Path(__file__).resolve().parents[1] / "database" / "overseer_trades.db")

conn = sqlite3.connect(DB_PATH, timeout=60)
cur = conn.cursor()

cur.execute("SELECT id, symbol, direction, gate_states_json, framework_scores_json, bias_breakdown_json FROM signal_log ORDER BY id")
rows = cur.fetchall()
print(f"Total signals: {len(rows)}")

updated_fw = 0
updated_bias = 0
batch = []

for sig_id, symbol, direction, gs_json, fw_json, bias_json in rows:
    changed = False

    old_fw = json.loads(fw_json) if fw_json else {}
    old_bias = json.loads(bias_json) if bias_json else {}

    if "FW19_fundamental" not in old_fw:
        gate_states = json.loads(gs_json) if gs_json else {}
        old_fw["FW19_fundamental"] = 1.0 if gate_states.get("gate_FUND", False) else 0.0
        changed = True
        updated_fw += 1

    if "fundamental_bias" not in old_bias:
        try:
            fund_adj = get_fundamental_bias_adjustment(symbol, direction or "BUY")
            old_bias["fundamental_bias"] = round(fund_adj, 6)
        except Exception:
            old_bias["fundamental_bias"] = 0.0
        changed = True
        updated_bias += 1

    if changed:
        batch.append((json.dumps(old_fw, sort_keys=True), json.dumps(old_bias, sort_keys=True), sig_id))

    if len(batch) >= 200:
        for _ in range(20):
            try:
                cur.executemany(
                    "UPDATE signal_log SET framework_scores_json = ?, bias_breakdown_json = ? WHERE id = ?",
                    batch,
                )
                conn.commit()
                batch = []
                break
            except sqlite3.OperationalError:
                time.sleep(1.0)

if batch:
    for _ in range(20):
        try:
            cur.executemany(
                "UPDATE signal_log SET framework_scores_json = ?, bias_breakdown_json = ? WHERE id = ?",
                batch,
            )
            conn.commit()
            break
        except sqlite3.OperationalError:
            time.sleep(1.0)

conn.close()
print(f"Updated FW19 in {updated_fw} signals")
print(f"Updated fundamental_bias in {updated_bias} signals")
