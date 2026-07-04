import sqlite3
conn = sqlite3.connect('database/overseer_trades.db')
c = conn.cursor()
c.execute("SELECT id, symbol, tick_bid, tick_ask FROM signal_log ORDER BY id DESC LIMIT 10")
for r in c.fetchall():
    print(f"  #{r[0]} {r[1]} bid={r[2]} ask={r[3]}")
conn.close()
