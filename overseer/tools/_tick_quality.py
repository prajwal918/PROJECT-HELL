import sqlite3
conn = sqlite3.connect('database/overseer_trades.db')
c = conn.cursor()

c.execute("SELECT symbol, COUNT(*) FROM tick_log WHERE bid > 0 AND ask > bid GROUP BY symbol ORDER BY COUNT(*) DESC")
print("=== Ticks with proper spread (bid < ask) ===")
for r in c.fetchall():
    print(f"  {r[0]}: {r[1]:,}")

c.execute("SELECT symbol, COUNT(*) FROM tick_log WHERE bid = ask AND bid > 0 GROUP BY symbol ORDER BY COUNT(*) DESC")
print("\n=== Ticks with bid == ask (no spread) ===")
for r in c.fetchall():
    print(f"  {r[0]}: {r[1]:,}")

c.execute("SELECT source, COUNT(*) FROM signal_log GROUP BY source")
print("\n=== Signal sources ===")
for r in c.fetchall():
    print(f"  {r[0]}: {r[1]}")

conn.close()
