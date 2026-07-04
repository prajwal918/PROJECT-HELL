import sqlite3
conn = sqlite3.connect('database/overseer_trades.db')
c = conn.cursor()
OOS_START_ID = 35761

for thr in [0.70, 0.75, 0.80, 0.85, 0.90]:
    c.execute("""
        SELECT symbol, direction,
               COUNT(*) as n,
               SUM(CASE WHEN outcome_200ticks='WIN' THEN 1 ELSE 0 END) as w,
               SUM(CASE WHEN outcome_200ticks='LOSS' THEN 1 ELSE 0 END) as l
        FROM signal_log
        WHERE id >= ? AND score >= ? AND outcome_200ticks IS NOT NULL AND outcome_200ticks != 'FLAT'
        GROUP BY symbol, direction
        HAVING n >= 5
        ORDER BY w*1.0/n DESC
    """, (OOS_START_ID, thr))
    print(f"\nScore >= {thr}:")
    for r in c.fetchall():
        wr = r[3]*100/max(r[3]+r[4],1)
        print(f"  {r[0]} {r[1]}: n={r[2]} W={r[3]} L={r[4]} WR={wr:.0f}%")

c.execute("""
    SELECT symbol, direction, 
           ROUND(adjusted_score, 2) as score_bucket,
           COUNT(*) as n,
           SUM(CASE WHEN outcome_200ticks='WIN' THEN 1 ELSE 0 END) as w,
           SUM(CASE WHEN outcome_200ticks='LOSS' THEN 1 ELSE 0 END) as l
    FROM signal_log
    WHERE id >= ? AND outcome_200ticks IS NOT NULL AND outcome_200ticks != 'FLAT'
    GROUP BY symbol, direction, score_bucket
    HAVING n >= 3
    ORDER BY w*1.0/n DESC
    LIMIT 20
""", (OOS_START_ID,))
print("\n\nTop 20 symbol+direction+score_bucket combos (OOS):")
for r in c.fetchall():
    wr = r[4]*100/max(r[4]+r[5],1)
    print(f"  {r[0]} {r[1]} score~{r[2]}: n={r[3]} W={r[4]} L={r[5]} WR={wr:.0f}%")

conn.close()
