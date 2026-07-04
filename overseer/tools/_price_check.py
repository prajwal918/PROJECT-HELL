import sqlite3
conn = sqlite3.connect('database/overseer_trades.db')
c = conn.cursor()
c.execute("SELECT symbol, bid, ask FROM tick_log WHERE symbol='6JM6' ORDER BY rowid DESC LIMIT 5")
print("6JM6 tick_log prices:")
for r in c.fetchall():
    print(f"  bid={r[1]} ask={r[2]}")
c.execute("SELECT symbol, bid, ask FROM tick_log WHERE symbol='6EM6' ORDER BY rowid DESC LIMIT 5")
print("\n6EM6 tick_log prices:")
for r in c.fetchall():
    print(f"  bid={r[1]} ask={r[2]}")
c.execute("SELECT symbol, bid, ask FROM tick_log WHERE symbol='6AM6' ORDER BY rowid DESC LIMIT 5")
print("\n6AM6 tick_log prices:")
for r in c.fetchall():
    print(f"  bid={r[1]} ask={r[2]}")
conn.close()
