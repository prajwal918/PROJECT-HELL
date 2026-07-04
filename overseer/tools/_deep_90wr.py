import sqlite3, json
conn = sqlite3.connect('database/overseer_trades.db')
c = conn.cursor()
OOS_START_ID = 35761

c.execute("""
    SELECT id, symbol, direction, score, adjusted_score,
           framework_scores_json, l3_features_json, bias_breakdown_json,
           spread_bps, risk_regime, session, dxy,
           outcome_10ticks, outcome_50ticks, outcome_200ticks
    FROM signal_log
    WHERE id >= ? AND symbol='6BM6' AND direction='BUY' AND score >= 0.80
      AND outcome_200ticks IS NOT NULL AND outcome_200ticks != 'FLAT'
    ORDER BY id
""", (OOS_START_ID,))
rows = c.fetchall()
print(f"6BM6 BUY score>=0.80: {len(rows)} signals")
wins = 0
losses = 0
for r in rows:
    fw = json.loads(r[5]) if r[5] else {}
    l3 = json.loads(r[6]) if r[6] else {}
    bias = json.loads(r[7]) if r[7] else {}
    if r[14] == 'WIN':
        wins += 1
        tag = "W"
    else:
        losses += 1
        tag = "L"
    print(f"  #{r[0]} score={r[3]:.3f} adj={r[4]:.3f} session={r[11]} regime={r[10]} spread={r[9]} dxy={r[12]} FW01={fw.get('FW01_multi_tf_trend',0):.2f} FW04={fw.get('FW04_liquidity_sweep',0):.2f} FW06={fw.get('FW06_session_kz',0):.2f} FW15={fw.get('FW15_l3_flow',0):.4f} [{tag}]")

print(f"\nWins={wins} Losses={losses} WR={wins*100/max(wins+losses,1):.0f}%")

c.execute("""
    SELECT symbol, direction, score, session, risk_regime, spread_bps,
           framework_scores_json, outcome_200ticks
    FROM signal_log
    WHERE id >= ? AND outcome_200ticks IS NOT NULL AND outcome_200ticks != 'FLAT'
    ORDER BY id
""", (OOS_START_ID,))
all_rows = c.fetchall()

from collections import defaultdict
combos = defaultdict(lambda: [0, 0])
for r in all_rows:
    fw = json.loads(r[6]) if r[6] else {}
    key = (r[0], r[1], f"FW06>={fw.get('FW06_session_kz',0):.1f}")
    if r[7] == 'WIN':
        combos[key][0] += 1
    else:
        combos[key][1] += 1

print("\n\nSession gate (FW06) impact on WR:")
for key, counts in sorted(combos.items(), key=lambda x: x[1][0]/max(sum(x[1]),1), reverse=True)[:15]:
    n = sum(counts)
    wr = counts[0]*100/n if n > 0 else 0
    if n >= 5:
        print(f"  {key[0]} {key[1]} {key[2]}: n={n} W={counts[0]} L={counts[1]} WR={wr:.0f}%")

conn.close()
