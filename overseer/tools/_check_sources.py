import sqlite3
conn = sqlite3.connect('database/overseer_trades.db')
cur = conn.cursor()

cur.execute("SELECT symbol, COUNT(*) FROM signal_log WHERE id > 41850 GROUP BY symbol ORDER BY symbol")
print("Recent signals by symbol:")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

cur.execute("SELECT symbol, COUNT(*) FROM tick_log GROUP BY symbol ORDER BY COUNT(*) DESC")
print("\nAll tick_log by symbol:")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}")

cur.execute("SELECT COUNT(*) FROM tick_log WHERE symbol LIKE 'GBP%' OR symbol LIKE 'EUR%' OR symbol LIKE 'AUD%'")
spot = cur.fetchone()[0]
print(f"\nSpot forex ticks (non-CME): {spot}")

conn.close()
