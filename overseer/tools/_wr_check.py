import sqlite3
conn = sqlite3.connect('database/overseer_trades.db')
c = conn.cursor()
c.execute("""
    SELECT symbol, 
           COUNT(*) as total,
           SUM(CASE WHEN outcome_10ticks='WIN' THEN 1 ELSE 0 END) as w10,
           SUM(CASE WHEN outcome_10ticks='LOSS' THEN 1 ELSE 0 END) as l10,
           SUM(CASE WHEN outcome_10ticks='FLAT' THEN 1 ELSE 0 END) as f10,
           SUM(CASE WHEN outcome_200ticks='WIN' THEN 1 ELSE 0 END) as w200,
           SUM(CASE WHEN outcome_200ticks='LOSS' THEN 1 ELSE 0 END) as l200,
           SUM(CASE WHEN outcome_200ticks='FLAT' THEN 1 ELSE 0 END) as f200
    FROM signal_log 
    WHERE outcome_200ticks IS NOT NULL
    GROUP BY symbol
""")
for r in c.fetchall():
    total = r[1]
    w200 = r[4]
    l200 = r[5]
    f200 = r[6]
    wr200 = w200*100/max(w200+l200,1)
    print(f"{r[0]}: n={total} 10t[W={r[2]} L={r[3]}] 200t[W={w200} L={l200} F={f200}] WR200={wr200:.1f}%")
conn.close()
