import sqlite3, json
conn = sqlite3.connect('database/overseer_trades.db')
c = conn.cursor()
c.execute("""
    SELECT symbol, direction, score, adjusted_score, 
           framework_scores_json, outcome_10ticks, outcome_50ticks, outcome_200ticks
    FROM signal_log 
    WHERE outcome_200ticks IS NOT NULL AND outcome_200ticks != 'FLAT'
""")
wins = []
losses = []
fw_names = None
for r in c.fetchall():
    fw = json.loads(r[4]) if r[4] else {}
    if fw_names is None:
        fw_names = sorted(fw.keys())
    if r[7] == 'WIN':
        wins.append(fw)
    elif r[7] == 'LOSS':
        losses.append(fw)

print(f"200-tick outcomes: {len(wins)} WIN, {len(losses)} LOSS")
if not wins or not losses:
    print("Not enough data yet")
    conn.close()
    exit()

print(f"\nFramework score averages (WIN vs LOSS):")
print(f"{'Framework':<30} {'WIN avg':>10} {'LOSS avg':>10} {'Diff':>10}")
for name in (fw_names or []):
    w_avg = sum(w.get(name, 0) for w in wins) / len(wins)
    l_avg = sum(l.get(name, 0) for l in losses) / len(losses)
    diff = w_avg - l_avg
    marker = " ***" if abs(diff) > 0.05 else ""
    print(f"{name:<30} {w_avg:>10.4f} {l_avg:>10.4f} {diff:>+10.4f}{marker}")

c.execute("""
    SELECT direction, COUNT(*), 
           SUM(CASE WHEN outcome_200ticks='WIN' THEN 1 ELSE 0 END),
           SUM(CASE WHEN outcome_200ticks='LOSS' THEN 1 ELSE 0 END)
    FROM signal_log 
    WHERE outcome_200ticks IS NOT NULL AND outcome_200ticks != 'FLAT'
    GROUP BY direction
""")
print(f"\nDirection WR:")
for r in c.fetchall():
    wr = r[2]*100/max(r[2]+r[3],1)
    print(f"  {r[0]}: n={r[1]} W={r[2]} L={r[3]} WR={wr:.1f}%")

c.execute("""
    SELECT symbol, COUNT(*), 
           SUM(CASE WHEN outcome_200ticks='WIN' THEN 1 ELSE 0 END),
           SUM(CASE WHEN outcome_200ticks='LOSS' THEN 1 ELSE 0 END)
    FROM signal_log 
    WHERE outcome_200ticks IS NOT NULL AND outcome_200ticks != 'FLAT'
    GROUP BY symbol
""")
print(f"\nSymbol WR at 200 ticks:")
for r in c.fetchall():
    wr = r[2]*100/max(r[2]+r[3],1)
    print(f"  {r[0]}: n={r[1]} W={r[2]} L={r[3]} WR={wr:.1f}%")

conn.close()
