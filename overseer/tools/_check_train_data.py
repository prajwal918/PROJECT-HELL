import sqlite3, json
conn = sqlite3.connect('database/overseer_trades.db')
cur = conn.cursor()

cur.execute("SELECT id, framework_scores_json FROM signal_log ORDER BY id DESC LIMIT 5")
for row in cur.fetchall():
    fs = json.loads(row[1]) if row[1] else {}
    has_fw17 = 'FW17_volume_profile' in fs
    has_fw18 = 'FW18_technical' in fs
    print(f"  id={row[0]}  FW17={has_fw17} FW18={has_fw18}  keys={len(fs)}")

cur.execute("SELECT COUNT(*) FROM signal_log WHERE outcome_200ticks IS NOT NULL AND outcome_200ticks != 'FLAT'")
n = cur.fetchone()[0]
print(f"\nTotal non-FLAT decided outcomes: {n}")

cur.execute("SELECT MIN(id) FROM signal_log WHERE framework_scores_json LIKE '%FW17_volume_profile%'")
r = cur.fetchone()
print(f"First signal with FW17: id={r[0]}")

if r[0]:
    cur.execute("SELECT COUNT(*) FROM signal_log WHERE id >= ? AND outcome_200ticks IS NOT NULL AND outcome_200ticks != 'FLAT'", (r[0],))
    n2 = cur.fetchone()[0]
    print(f"Non-FLAT signals with FW17+FW18: {n2}")

conn.close()
