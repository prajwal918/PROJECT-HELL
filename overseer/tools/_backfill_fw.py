import json
import sqlite3
import sys
import time
from pathlib import Path

DB_PATH = "database/overseer_trades.db"

FW17_GATES = {"gate_VP": 1.5, "gate_TPO": 1.0, "gate_VWAP": 1.0}
FW17_TOTAL = sum(FW17_GATES.values())
FW18_GATES = {"gate_RSI": 1.0, "gate_MACD": 1.0, "gate_BB": 1.0}
FW18_TOTAL = sum(FW18_GATES.values())

conn = sqlite3.connect(DB_PATH, timeout=60)
cur = conn.cursor()

cur.execute("SELECT id, gate_states_json, framework_scores_json FROM signal_log ORDER BY id")
rows = cur.fetchall()
print(f"Total signals: {len(rows)}")

updated = 0
batch = []
for sig_id, gs_json, fw_json in rows:
    if not gs_json:
        continue
    gate_states = json.loads(gs_json)
    old_fw = json.loads(fw_json) if fw_json else {}

    if "FW17_volume_profile" in old_fw and "FW18_technical" in old_fw:
        continue

    earned17 = sum(w for g, w in FW17_GATES.items() if gate_states.get(g, False))
    old_fw["FW17_volume_profile"] = round(earned17 / FW17_TOTAL, 4)

    earned18 = sum(w for g, w in FW18_GATES.items() if gate_states.get(g, False))
    old_fw["FW18_technical"] = round(earned18 / FW18_TOTAL, 4)

    gate_dd = gate_states.get("gate_DD", False)
    gate_imb = gate_states.get("gate_IMB", False)
    if "FW03_volume" in old_fw:
        fw03_gates = {"gate_F": 1.0, "gate_G": 1.0, "gate_VOL": 1.5, "gate_DD": 0.5, "gate_IMB": 0.5}
        fw03_total = sum(fw03_gates.values())
        earned03 = sum(w for g, w in fw03_gates.items() if gate_states.get(g, False))
        old_fw["FW03_volume"] = round(earned03 / fw03_total, 4)

    if "FW02_price_action" in old_fw:
        fw02_gates = {"gate_C": 1.0, "gate_E": 1.0, "gate_SR": 0.5}
        fw02_total = sum(fw02_gates.values())
        earned02 = sum(w for g, w in fw02_gates.items() if gate_states.get(g, False))
        old_fw["FW02_price_action"] = round(earned02 / fw02_total, 4)

    batch.append((json.dumps(old_fw, sort_keys=True), sig_id))
    updated += 1

    if len(batch) >= 100:
        for _ in range(20):
            try:
                cur.executemany(
                    "UPDATE signal_log SET framework_scores_json = ? WHERE id = ?",
                    batch,
                )
                conn.commit()
                batch = []
                break
            except sqlite3.OperationalError:
                time.sleep(1.0)
        if batch:
            print(f"  stuck at signal {sig_id}, retrying...")
            time.sleep(2.0)

if batch:
    for _ in range(20):
        try:
            cur.executemany(
                "UPDATE signal_log SET framework_scores_json = ? WHERE id = ?",
                batch,
            )
            conn.commit()
            batch = []
            break
        except sqlite3.OperationalError:
            time.sleep(1.0)
conn.close()
print(f"Updated {updated} signals with FW17 + FW18 scores")
