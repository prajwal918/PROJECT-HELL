import sqlite3
conn = sqlite3.connect('database/overseer_trades.db')
c = conn.cursor()

c.execute("""
    SELECT symbol, COUNT(*) as ticks, MIN(timestamp) as first_t, MAX(timestamp) as last_t 
    FROM tick_log 
    WHERE timestamp > datetime('now','-30 minutes') 
    GROUP BY symbol 
    ORDER BY ticks DESC
""")
for r in c.fetchall():
    print(f'{r[0]}: {r[1]} ticks from {r[2]} to {r[3]}')

c.execute("""
    SELECT id, symbol, score, timestamp 
    FROM signal_log 
    WHERE id >= 40000 
    ORDER BY id DESC 
    LIMIT 20
""")
print('\nRecent signals:')
for r in c.fetchall():
    print(f'  #{r[0]} {r[1]} score={r[2]:.4f} at {r[3]}')

# Check for gap patterns - time between consecutive signals
c.execute("""
    SELECT id, symbol, timestamp, 
           JULIANDAY(timestamp) - JULIANDAY(LAG(timestamp) OVER (ORDER BY id)) as gap_days
    FROM signal_log 
    WHERE id >= 39510 
    ORDER BY id
""")
gaps = []
for r in c.fetchall():
    if r[3] is not None:
        gap_sec = r[3] * 86400
        if gap_sec > 30:
            gaps.append((r[0], r[1], r[2], gap_sec))

print(f'\nGaps > 30s between signals: {len(gaps)}')
for g in gaps[:10]:
    print(f'  #{g[0]} {g[1]} at {g[2]} gap={g[3]:.0f}s')

conn.close()
