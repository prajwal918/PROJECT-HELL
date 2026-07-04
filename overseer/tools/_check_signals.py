import sqlite3
import json

conn = sqlite3.connect("database/overseer_trades.db")

cur = conn.execute("SELECT COUNT(*) FROM signal_log WHERE outcome_200ticks IS NOT NULL AND outcome_200ticks != 'FLAT'")
print("Non-FLAT outcomes:", cur.fetchone()[0])

cur = conn.execute("SELECT COUNT(*) FROM signal_log WHERE outcome_200ticks IS NOT NULL")
print("With any outcome:", cur.fetchone()[0])

cur = conn.execute("SELECT COUNT(*) FROM signal_log")
print("All signals:", cur.fetchone()[0])

cur = conn.execute("SELECT bias_breakdown_json FROM signal_log WHERE outcome_200ticks IS NOT NULL AND outcome_200ticks != 'FLAT' ORDER BY id DESC LIMIT 5")
for row in cur.fetchall():
    bias = json.loads(row[0]) if row[0] else {}
    fund = bias.get("bias_fundamental", bias.get("fundamental_bias", "MISSING"))
    print("  bias_fundamental:", fund)

cur = conn.execute("SELECT framework_scores_json FROM signal_log WHERE outcome_200ticks IS NOT NULL AND outcome_200ticks != 'FLAT' ORDER BY id DESC LIMIT 5")
for row in cur.fetchall():
    fw = json.loads(row[0]) if row[0] else {}
    fw19 = fw.get("FW19_fundamental", "MISSING")
    print("  FW19_fundamental:", fw19, "  fw_count:", len(fw))

cur = conn.execute("SELECT bias_breakdown_json FROM signal_log WHERE outcome_200ticks IS NOT NULL AND outcome_200ticks != 'FLAT' ORDER BY id ASC LIMIT 5")
print("Oldest signals:")
for row in cur.fetchall():
    bias = json.loads(row[0]) if row[0] else {}
    fund = bias.get("bias_fundamental", bias.get("fundamental_bias", "MISSING"))
    print("  bias_fundamental:", fund)

conn.close()
