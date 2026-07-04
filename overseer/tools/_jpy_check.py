import sqlite3
conn = sqlite3.connect('database/overseer_trades.db')
c = conn.cursor()
c.execute("SELECT id, symbol, tick_bid, tick_ask, outcome_10ticks, outcome_50ticks, outcome_200ticks FROM signal_log WHERE symbol='6JM6' AND outcome_200ticks IS NOT NULL ORDER BY id DESC LIMIT 5")
for r in c.fetchall():
    mid = (r[2]+r[3])/2 if r[2] and r[3] else 0
    print(f'  #{r[0]} {r[1]} bid={r[2]} ask={r[3]} mid={mid:.5f} o10={r[4]} o50={r[5]} o200={r[6]}')
c.execute("SELECT id, symbol, tick_bid, tick_ask, outcome_10ticks, outcome_50ticks, outcome_200ticks FROM signal_log WHERE symbol='6CM6' AND outcome_10ticks IS NOT NULL ORDER BY id DESC LIMIT 5")
print("\n6CM6:")
for r in c.fetchall():
    mid = (r[2]+r[3])/2 if r[2] and r[3] else 0
    print(f'  #{r[0]} {r[1]} bid={r[2]} ask={r[3]} mid={mid:.5f} o10={r[4]} o50={r[5]} o200={r[6]}')
conn.close()
