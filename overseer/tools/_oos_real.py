import sqlite3
conn = sqlite3.connect('database/overseer_trades.db')
c = conn.cursor()
OOS_START_ID = 35761

for thr in [0.50, 0.55, 0.60, 0.65, 0.70, 0.75]:
    c.execute("SELECT COUNT(*) FROM signal_log WHERE id >= ? AND score >= ? AND outcome_200ticks IS NOT NULL AND outcome_200ticks != 'FLAT'", (OOS_START_ID, thr))
    n = c.fetchone()[0]
    c.execute("SELECT SUM(CASE WHEN outcome_200ticks='WIN' THEN 1 ELSE 0 END), SUM(CASE WHEN outcome_200ticks='LOSS' THEN 1 ELSE 0 END) FROM signal_log WHERE id >= ? AND score >= ? AND outcome_200ticks IS NOT NULL AND outcome_200ticks != 'FLAT'", (OOS_START_ID, thr))
    r = c.fetchone()
    c.execute("SELECT COUNT(*) FROM signal_log WHERE id >= ? AND score >= ? AND outcome_200ticks IS NULL", (OOS_START_ID, thr))
    pending = c.fetchone()[0]
    if n > 0:
        wr = r[0]*100/n
        print(f"OOS Score>={thr}: n={n} W={r[0]} L={r[1]} WR={wr:.1f}% pending={pending}")
    else:
        print(f"OOS Score>={thr}: no resolved non-FLAT yet, pending={pending}")

conn.close()
