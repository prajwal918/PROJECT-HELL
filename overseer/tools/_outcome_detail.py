import sqlite3
conn = sqlite3.connect('database/overseer_trades.db')
c = conn.cursor()
c.execute("SELECT symbol, outcome_10ticks, outcome_50ticks, outcome_200ticks, COUNT(*) FROM signal_log GROUP BY symbol, outcome_10ticks, outcome_50ticks, outcome_200ticks ORDER BY symbol, outcome_200ticks")
for r in c.fetchall():
    if r[4] > 0 and r[0].startswith("6"):
        print(f"  {r[0]} 10t={r[1]} 50t={r[2]} 200t={r[3]} count={r[4]}")
conn.close()
