import sqlite3, json

conn = sqlite3.connect('database/overseer_trades.db')
c = conn.cursor()
c.execute('SELECT COUNT(*) FROM tick_log')
total_ticks = c.fetchone()[0]
c.execute('SELECT COUNT(*) FROM signal_log')
total_signals = c.fetchone()[0]
print(f'Total ticks: {total_ticks:,}')
print(f'Total signals: {total_signals}')
print(f'Signal rate: 1 signal per {total_ticks/max(1,total_signals):,.0f} ticks')
print()

c.execute('SELECT MIN(timestamp), MAX(timestamp) FROM signal_log')
r = c.fetchone()
print(f'First signal: {r[0]}')
print(f'Last signal: {r[1]}')

c.execute('SELECT adjusted_score, COUNT(*) FROM signal_log GROUP BY adjusted_score ORDER BY adjusted_score')
print('\nScore distribution:')
for r in c.fetchall():
    print(f'  score={r[0]:.4f}: {r[1]} signals')

c.execute('SELECT direction, COUNT(*) FROM signal_log GROUP BY direction')
print('\nDirection distribution:')
for r in c.fetchall():
    print(f'  {r[0]}: {r[1]}')

c.execute("""
SELECT
    SUM(CASE WHEN outcome_10ticks='WIN' THEN 1 ELSE 0 END),
    SUM(CASE WHEN outcome_10ticks='LOSS' THEN 1 ELSE 0 END),
    SUM(CASE WHEN outcome_10ticks='FLAT' THEN 1 ELSE 0 END),
    SUM(CASE WHEN outcome_50ticks='WIN' THEN 1 ELSE 0 END),
    SUM(CASE WHEN outcome_50ticks='LOSS' THEN 1 ELSE 0 END),
    SUM(CASE WHEN outcome_50ticks='FLAT' THEN 1 ELSE 0 END),
    SUM(CASE WHEN outcome_200ticks='WIN' THEN 1 ELSE 0 END),
    SUM(CASE WHEN outcome_200ticks='LOSS' THEN 1 ELSE 0 END),
    SUM(CASE WHEN outcome_200ticks='FLAT' THEN 1 ELSE 0 END)
FROM signal_log
""")
r = c.fetchone()
print('\nOutcome summary:')
w10, l10, f10 = r[0], r[1], r[2]
w50, l50, f50 = r[3], r[4], r[5]
w200, l200, f200 = r[6], r[7], r[8]
print(f'  10t:  WIN={w10} LOSS={l10} FLAT={f10}  WR={w10/max(1,w10+l10)*100:.0f}%')
print(f'  50t:  WIN={w50} LOSS={l50} FLAT={f50}  WR={w50/max(1,w50+l50)*100:.0f}%')
print(f'  200t: WIN={w200} LOSS={l200} FLAT={f200}  WR={w200/max(1,w200+l200)*100:.0f}%')

# Per-symbol outcome analysis
print('\nPer-symbol outcomes (200t):')
c.execute("""
SELECT symbol, direction,
    SUM(CASE WHEN outcome_200ticks='WIN' THEN 1 ELSE 0 END),
    SUM(CASE WHEN outcome_200ticks='LOSS' THEN 1 ELSE 0 END),
    AVG(adjusted_score),
    AVG(CASE WHEN framework_scores_json != '' THEN json_extract(framework_scores_json, '$.FW15_l3_flow') END)
FROM signal_log
GROUP BY symbol
ORDER BY symbol
""")
for r in c.fetchall():
    wr = r[2]/max(1,r[2]+r[3])*100
    print(f'  {r[0]}: WIN={r[2]} LOSS={r[3]} WR={wr:.0f}% avg_score={r[4]:.4f} avg_FW15={r[5] if r[5] else 0:.4f}')

# Score vs outcome
print('\nScore vs outcome_200t:')
c.execute("SELECT adjusted_score, outcome_200ticks FROM signal_log WHERE outcome_200ticks IS NOT NULL")
wins = []
losses = []
for r in c.fetchall():
    if r[1] == 'WIN':
        wins.append(r[0])
    elif r[1] == 'LOSS':
        losses.append(r[0])
if wins:
    print(f'  WIN avg score: {sum(wins)/len(wins):.4f}')
if losses:
    print(f'  LOSS avg score: {sum(losses)/len(losses):.4f}')

# FW15 vs outcome
print('\nFW15_l3_flow vs outcome_200t:')
c.execute("SELECT framework_scores_json, outcome_200ticks FROM signal_log WHERE outcome_200ticks IS NOT NULL")
for r in c.fetchall():
    fw = json.loads(r[0]) if r[0] else {}
    fw15 = fw.get('FW15_l3_flow', 0)
    print(f'  FW15={fw15:.4f} outcome={r[1]}')

conn.close()
