import sqlite3
conn = sqlite3.connect('database/overseer_trades.db')
c = conn.cursor()
c.execute('SELECT COUNT(*) FROM signal_log')
total = c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM signal_log WHERE outcome_10ticks IS NOT NULL")
has_outcome = c.fetchone()[0]
c.execute('SELECT COUNT(DISTINCT symbol) FROM signal_log')
symbols = c.fetchone()[0]
c.execute('SELECT symbol, direction, COUNT(*), MIN(adjusted_score), MAX(adjusted_score) FROM signal_log GROUP BY symbol, direction ORDER BY COUNT(*) DESC LIMIT 10')
print(f'Total signals: {total:,}')
print(f'With outcomes: {has_outcome:,}')
print(f'Unique symbols: {symbols}')
print()
print('Top symbol/direction combos:')
for r in c.fetchall():
    print(f'  {r[0]} {r[1]}: {r[2]:,} score=[{r[3]:.4f}, {r[4]:.4f}]')
c.execute('SELECT id, symbol, direction, outcome_10ticks, outcome_50ticks, outcome_200ticks FROM signal_log WHERE outcome_10ticks IS NOT NULL ORDER BY id DESC LIMIT 5')
print()
print('Recent outcomes:')
for r in c.fetchall():
    print(f'  #{r[0]} {r[1]} {r[2]}: o10={r[3]} o50={r[4]} o200={r[5]}')
conn.close()
