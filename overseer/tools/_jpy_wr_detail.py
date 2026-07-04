import sqlite3
conn = sqlite3.connect('database/overseer_trades.db')
c = conn.cursor()
c.execute("SELECT outcome_200ticks, COUNT(*) FROM signal_log WHERE symbol='6JM6' GROUP BY outcome_200ticks")
print("6JM6 200t outcomes:")
for r in c.fetchall():
    print(f"  {r[0]}: {r[1]:,}")
c.execute("SELECT outcome_10ticks, COUNT(*) FROM signal_log WHERE symbol='6JM6' GROUP BY outcome_10ticks")
print("\n6JM6 10t outcomes:")
for r in c.fetchall():
    print(f"  {r[0]}: {r[1]:,}")
conn.close()
