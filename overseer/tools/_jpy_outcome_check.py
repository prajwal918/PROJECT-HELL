import sqlite3
conn = sqlite3.connect('database/overseer_trades.db')
c = conn.cursor()
c.execute("SELECT id, tick_bid, tick_ask, outcome_10ticks, outcome_50ticks, outcome_200ticks FROM signal_log WHERE symbol='6JM6' AND outcome_200ticks IS NOT NULL LIMIT 5")
for r in c.fetchall():
    print(f"  #{r[0]} bid={r[1]} ask={r[2]} o10={r[3]} o50={r[4]} o200={r[5]}")
conn.close()
