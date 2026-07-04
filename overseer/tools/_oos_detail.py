import sqlite3
conn = sqlite3.connect('database/overseer_trades.db')
c = conn.cursor()
OOS_START_ID = 35761

c.execute("""
    SELECT symbol, direction,
           COUNT(*) as n,
           SUM(CASE WHEN outcome_200ticks='WIN' THEN 1 ELSE 0 END) as w,
           SUM(CASE WHEN outcome_200ticks='LOSS' THEN 1 ELSE 0 END) as l
    FROM signal_log
    WHERE id >= ? AND score >= 0.60 AND outcome_200ticks IS NOT NULL AND outcome_200ticks != 'FLAT'
    GROUP BY symbol, direction
    ORDER BY n DESC
""", (OOS_START_ID,))
print("OOS WR by symbol+direction (score>=0.60):")
for r in c.fetchall():
    wr = r[3]*100/max(r[3]+r[4],1)
    print(f"  {r[0]} {r[1]}: n={r[2]} W={r[3]} L={r[4]} WR={wr:.0f}%")

c.execute("""
    SELECT symbol,
           COUNT(*) as n,
           SUM(CASE WHEN outcome_50ticks='WIN' THEN 1 ELSE 0 END) as w,
           SUM(CASE WHEN outcome_50ticks='LOSS' THEN 1 ELSE 0 END) as l
    FROM signal_log
    WHERE id >= ? AND score >= 0.60 AND outcome_50ticks IS NOT NULL AND outcome_50ticks != 'FLAT'
    GROUP BY symbol
    ORDER BY n DESC
""", (OOS_START_ID,))
print("\nOOS WR by symbol at 50-tick (score>=0.60):")
for r in c.fetchall():
    wr = r[2]*100/max(r[2]+r[3],1)
    print(f"  {r[0]}: n={r[2]+r[3]} W={r[2]} L={r[3]} WR={wr:.0f}%")

conn.close()
