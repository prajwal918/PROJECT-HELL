import sqlite3
conn = sqlite3.connect('database/overseer_trades.db')
cur = conn.cursor()
cur.execute("SELECT symbol, direction, COUNT(*) as total, SUM(CASE WHEN outcome_200ticks='WIN' THEN 1 ELSE 0 END) as wins, SUM(CASE WHEN outcome_200ticks='LOSS' THEN 1 ELSE 0 END) as losses FROM signal_log WHERE outcome_200ticks IS NOT NULL AND outcome_200ticks != 'FLAT' GROUP BY symbol, direction ORDER BY symbol, direction")
for row in cur.fetchall():
    sym, dire, total, wins, losses = row
    d = wins + losses
    wr = (wins/d*100) if d > 0 else 0
    print(f"  {sym} {dire}: W={wins} L={losses} WR={wr:.1f}% (n={d})")
conn.close()
