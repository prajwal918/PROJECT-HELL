import sqlite3
conn = sqlite3.connect('database/overseer_trades.db')
c = conn.cursor()
c.execute("SELECT outcome_200ticks, COUNT(*) FROM signal_log GROUP BY outcome_200ticks")
print("All 200t outcomes:")
for r in c.fetchall():
    print(f"  '{r[0]}': {r[1]:,}")
conn.close()
