import sqlite3
conn = sqlite3.connect('database/overseer_trades.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("""SELECT COUNT(*) as total,
    SUM(CASE WHEN outcome_200ticks='WIN' THEN 1 ELSE 0 END) as wins,
    SUM(CASE WHEN outcome_200ticks='LOSS' THEN 1 ELSE 0 END) as losses,
    SUM(CASE WHEN outcome_200ticks='FLAT' THEN 1 ELSE 0 END) as flats
FROM signal_log WHERE outcome_200ticks IS NOT NULL""")
row = cur.fetchone()
total = row['total']
wins = row['wins']
losses = row['losses']
flats = row['flats']
decided = wins + losses
wr = (wins/decided*100) if decided > 0 else 0
print(f"=== ALL SIGNALS (with outcomes) ===")
print(f"Total: {total}  WIN: {wins}  LOSS: {losses}  FLAT: {flats}")
print(f"WR (ex-FLAT): {wr:.1f}%  (decided={decided})")

print()
print("=== OOS SIGNALS BY SYMBOL+DIRECTION (id >= 35761) ===")
cur.execute("""SELECT symbol, direction, COUNT(*) as total,
    SUM(CASE WHEN outcome_200ticks='WIN' THEN 1 ELSE 0 END) as wins,
    SUM(CASE WHEN outcome_200ticks='LOSS' THEN 1 ELSE 0 END) as losses,
    SUM(CASE WHEN outcome_200ticks='FLAT' THEN 1 ELSE 0 END) as flats
FROM signal_log WHERE id >= 35761 AND outcome_200ticks IS NOT NULL
GROUP BY symbol, direction ORDER BY symbol, direction""")
for r in cur.fetchall():
    d = r['wins'] + r['losses']
    w = (r['wins']/d*100) if d > 0 else 0
    print(f"  {r['symbol']} {r['direction']}:  W={r['wins']} L={r['losses']} F={r['flats']}  WR={w:.1f}% (n={d})")

print()
print("=== OOS BUY SIGNALS BY SCORE THRESHOLD ===")
for thresh in [0.85, 0.90, 0.95]:
    cur.execute("""SELECT symbol, COUNT(*) as total,
        SUM(CASE WHEN outcome_200ticks='WIN' THEN 1 ELSE 0 END) as wins,
        SUM(CASE WHEN outcome_200ticks='LOSS' THEN 1 ELSE 0 END) as losses
        FROM signal_log WHERE id >= 35761 AND direction='BUY' AND score >= ? AND outcome_200ticks IS NOT NULL
        GROUP BY symbol ORDER BY symbol""", (thresh,))
    print(f"  --- threshold >= {thresh} ---")
    for r in cur.fetchall():
        d = r['wins'] + r['losses']
        w = (r['wins']/d*100) if d > 0 else 0
        print(f"    {r['symbol']}: W={r['wins']} L={r['losses']} WR={w:.1f}% (n={d})")

cur.execute("SELECT COUNT(*) FROM signal_log WHERE outcome_200ticks IS NULL")
pending = cur.fetchone()[0]
print(f"\nPending outcomes (NULL): {pending}")

cur.execute("SELECT COUNT(*) FROM signal_log")
total_signals = cur.fetchone()[0]
print(f"Total signals in DB: {total_signals}")

conn.close()
