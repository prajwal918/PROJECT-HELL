import sqlite3, json

conn = sqlite3.connect('database/overseer_trades.db')
c = conn.cursor()

print("=== SIGNAL LOG FULL INSPECTION ===\n")

c.execute("SELECT id,symbol,entry_price,tick_bid,tick_ask,outcome_10ticks,outcome_50ticks,outcome_200ticks FROM signal_log ORDER BY id")
for r in c.fetchall():
    print(f"Signal #{r[0]} {r[1]}: entry={r[2]} bid={r[3]} ask={r[4]} 10t={r[5]} 50t={r[6]} 200t={r[7]}")

print("\n=== RECENT TICKS PER SYMBOL ===\n")
for sym in ['6JM6', '6EM6', '6AM6', '6CM6', '6BM6']:
    c.execute(f"SELECT bid, ask, timestamp FROM tick_log WHERE symbol='{sym}' ORDER BY ROWID DESC LIMIT 3")
    rows = c.fetchall()
    if rows:
        print(f"{sym}:")
        for r in rows:
            mid = (r[0] + r[1]) / 2 if r[0] and r[1] else 0
            print(f"  bid={r[0]} ask={r[1]} mid={mid:.6f} ts={r[2]}")
    else:
        print(f"{sym}: NO TICKS")

print("\n=== SIGNAL LOGGER MID PRICE TRACKING ===\n")

# Check if signal_logger stores mid prices somewhere
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
print(f"All tables: {tables}")

# Check tick count since last signal
c.execute("SELECT COUNT(*) FROM tick_log WHERE timestamp > '2026-06-01 13:32:04'")
print(f"Ticks since last signal: {c.fetchone()[0]}")

# Check spread distribution
print("\n=== SPREAD DISTRIBUTION (tick_log) ===\n")
for sym in ['6JM6', '6EM6', '6AM6', '6CM6', '6BM6']:
    c.execute(f"SELECT AVG(ask-bid), MIN(ask-bid), MAX(ask-bid) FROM tick_log WHERE symbol='{sym}' AND bid > 0 AND ask > 0")
    r = c.fetchone()
    if r and r[0]:
        print(f"{sym}: avg_spread={r[0]:.6f} min={r[1]:.6f} max={r[2]:.6f}")

conn.close()
