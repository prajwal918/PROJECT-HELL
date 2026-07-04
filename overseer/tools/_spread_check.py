import sqlite3
conn = sqlite3.connect('database/overseer_trades.db')
c = conn.cursor()
c.execute("SELECT symbol, COUNT(*), SUM(CASE WHEN bid = ask THEN 1 ELSE 0 END), SUM(CASE WHEN bid != ask THEN 1 ELSE 0 END) FROM tick_log WHERE symbol LIKE '6E%' OR symbol LIKE '6A%' OR symbol LIKE '6B%' OR symbol LIKE '6J%' OR symbol LIKE '6C%' GROUP BY symbol")
for r in c.fetchall():
    print(f"{r[0]}: total={r[1]:,} bid==ask={r[2]:,} ({r[2]*100//max(r[1],1)}%) bid!=ask={r[3]:,}")
conn.close()
