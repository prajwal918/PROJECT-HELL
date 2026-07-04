# OVERSEER Status Check - run anytime
python -c "
import sqlite3, json; conn=sqlite3.connect('database/overseer_trades.db'); c=conn.cursor()
c.execute('SELECT COUNT(*) FROM tick_log'); ticks=c.fetchone()[0]
c.execute('SELECT COUNT(*) FROM signal_log'); signals=c.fetchone()[0]
c.execute('SELECT id,symbol,direction,score,adjusted_score,executed,timestamp FROM signal_log ORDER BY id DESC LIMIT 10'); rows=c.fetchall()
c.execute('SELECT COUNT(*) FROM signal_log WHERE outcome_200ticks IS NOT NULL'); outcomes=c.fetchone()[0]
print(f'=== OVERSEER STATUS ===')
print(f'Ticks ingested: {ticks:,}')
print(f'Signals logged: {signals}')
print(f'Outcomes tracked: {outcomes}')
print(f'')
if rows:
    print(f'Last 10 signals:')
    for r in rows:
        ex = 'EXECUTED' if r[5] else 'signal-only'
        print(f'  #{r[0]} {r[1]} {r[2]} score={r[3]:.4f} {ex} @ {r[6]}')
else:
    print('No signals yet')
conn.close()
"
