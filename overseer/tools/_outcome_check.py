import sqlite3
conn = sqlite3.connect('database/overseer_trades.db')
c = conn.cursor()
c.execute("SELECT outcome_10ticks, COUNT(*) FROM signal_log GROUP BY outcome_10ticks")
print("10-tick outcomes:")
for r in c.fetchall():
    print(f"  {r[0]}: {r[1]:,}")
c.execute("SELECT outcome_50ticks, COUNT(*) FROM signal_log GROUP BY outcome_50ticks")
print("\n50-tick outcomes:")
for r in c.fetchall():
    print(f"  {r[0]}: {r[1]:,}")
c.execute("SELECT outcome_200ticks, COUNT(*) FROM signal_log GROUP BY outcome_200ticks")
print("\n200-tick outcomes:")
for r in c.fetchall():
    print(f"  {r[0]}: {r[1]:,}")
c.execute("SELECT symbol, COUNT(*), SUM(CASE WHEN outcome_10ticks='WIN' THEN 1 ELSE 0 END), SUM(CASE WHEN outcome_10ticks='LOSS' THEN 1 ELSE 0 END), SUM(CASE WHEN outcome_10ticks='FLAT' THEN 1 ELSE 0 END) FROM signal_log GROUP BY symbol")
print("\nPer-symbol 10t outcomes:")
for r in c.fetchall():
    print(f"  {r[0]}: total={r[1]} W={r[2]} L={r[3]} F={r[4]}")
conn.close()
