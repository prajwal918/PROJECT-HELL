import sqlite3
conn = sqlite3.connect('database/overseer_trades.db')
c = conn.cursor()

c.execute("SELECT symbol, bid, ask FROM tick_log ORDER BY ROWID DESC LIMIT 10")
print("=== Latest 10 ticks ===")
for r in c.fetchall():
    bid, ask = r[1], r[2]
    mid = (bid + ask) / 2 if bid and ask else 0
    spread = ask - bid if bid and ask else 0
    print(f"  {r[0]} bid={bid:.6f} ask={ask:.6f} mid={mid:.6f} spread={spread:.6f}")

# Check how many ticks have bid==ask (bad)
c.execute("SELECT COUNT(*) FROM tick_log WHERE bid = ask AND bid > 0")
bad = c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM tick_log WHERE bid > 0 AND ask > 0 AND bid != ask")
good = c.fetchone()[0]
print(f"\nBid==Ask (bad): {bad:,}  Bid!=Ask (good): {good:,}")

conn.close()
