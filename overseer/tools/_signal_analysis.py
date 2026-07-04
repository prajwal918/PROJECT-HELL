"""Signal analysis deep-dive for OVERSEER."""
import sqlite3
import json
import sys

DB = "database/overseer_trades.db"
conn = sqlite3.connect(DB)
c = conn.cursor()

OOS_START = 35761

# 1. Gate pass rates for OOS signals with outcomes
c.execute("""
    SELECT gate_states_json, outcome_200ticks FROM signal_log 
    WHERE id >= ? AND outcome_200ticks IS NOT NULL AND outcome_200ticks != ''
""", (OOS_START,))
rows = c.fetchall()
total = len(rows)
print(f"=== GATE PASS RATES (OOS, n={total}) ===\n")

gate_pass = {}
gate_win_when_pass = {}
gate_win_when_fail = {}

for row in rows:
    try:
        gs = json.loads(row[0])
        outcome = row[1]
        is_win = outcome == "WIN"
        for gate, passed in gs.items():
            if gate not in gate_pass:
                gate_pass[gate] = {"pass": 0, "fail": 0, "win_pass": 0, "win_fail": 0, "total": 0}
            gate_pass[gate]["total"] += 1
            if passed:
                gate_pass[gate]["pass"] += 1
                if is_win:
                    gate_pass[gate]["win_pass"] += 1
            else:
                gate_pass[gate]["fail"] += 1
                if is_win:
                    gate_pass[gate]["win_fail"] += 1
    except Exception:
        pass

# Sort by edge (WR when pass - WR when fail)
gate_edge = []
for gate, data in gate_pass.items():
    pass_rate = data["pass"] / data["total"] * 100 if data["total"] > 0 else 0
    wr_pass = data["win_pass"] / data["pass"] * 100 if data["pass"] > 0 else 0
    wr_fail = data["win_fail"] / data["fail"] * 100 if data["fail"] > 0 else 0
    edge = wr_pass - wr_fail
    gate_edge.append((gate, pass_rate, wr_pass, wr_fail, edge, data["total"]))

gate_edge.sort(key=lambda x: x[4], reverse=True)

print(f"{'Gate':25s} {'Pass%':>6s} {'WR(P)':>6s} {'WR(F)':>6s} {'Edge':>6s} {'n':>6s}")
print("-" * 60)
for gate, pr, wp, wf, edge, n in gate_edge[:30]:
    print(f"{gate:25s} {pr:5.1f}% {wp:5.1f}% {wf:5.1f}% {edge:+5.1f}% {n:5d}")

print(f"\n--- WORST GATES (pass = lower WR) ---")
for gate, pr, wp, wf, edge, n in gate_edge[-10:]:
    print(f"{gate:25s} {pr:5.1f}% {wp:5.1f}% {wf:5.1f}% {edge:+5.1f}% {n:5d}")

# 2. Per-symbol analysis
print(f"\n=== PER-SYMBOL DIRECTION ANALYSIS ===\n")

for symbol in ["6BM6", "6AM6", "6CM6", "6EM6", "6JM6"]:
    for direction in ["BUY", "SELL"]:
        c.execute("""
            SELECT COUNT(*), 
                   SUM(CASE WHEN outcome_200ticks='WIN' THEN 1 ELSE 0 END),
                   AVG(score), AVG(adjusted_score)
            FROM signal_log 
            WHERE id >= ? AND symbol=? AND direction=?
            AND outcome_200ticks IS NOT NULL AND outcome_200ticks != ''
        """, (OOS_START, symbol, direction))
        row = c.fetchone()
        if row and row[0] > 0:
            n, wins, avg_score, avg_adj = row
            wr = wins/n*100 if n > 0 else 0
            print(f"  {symbol} {direction}: n={n:4d} WR={wr:5.1f}% avg_score={avg_score:.3f} avg_adj={avg_adj:.3f}")

# 3. Score distribution vs outcome
print(f"\n=== SCORE BINS vs WIN RATE (OOS) ===\n")
for lo, hi in [(0.50, 0.60), (0.60, 0.70), (0.70, 0.80), (0.80, 0.85), (0.85, 0.90), (0.90, 0.95), (0.95, 1.01)]:
    c.execute("""
        SELECT COUNT(*), SUM(CASE WHEN outcome_200ticks='WIN' THEN 1 ELSE 0 END)
        FROM signal_log 
        WHERE id >= ? AND score >= ? AND score < ?
        AND outcome_200ticks IS NOT NULL AND outcome_200ticks != ''
    """, (OOS_START, lo, hi))
    row = c.fetchone()
    if row and row[0] > 0:
        wr = row[1]/row[0]*100
        print(f"  [{lo:.2f}-{hi:.2f}): n={row[0]:4d} WR={wr:5.1f}%")

# 4. Adjusted score distribution
print(f"\n=== ADJUSTED SCORE BINS vs WIN RATE (OOS) ===\n")
for lo, hi in [(0.50, 0.70), (0.70, 0.85), (0.85, 0.90), (0.90, 0.95), (0.95, 1.01)]:
    c.execute("""
        SELECT COUNT(*), SUM(CASE WHEN outcome_200ticks='WIN' THEN 1 ELSE 0 END)
        FROM signal_log 
        WHERE id >= ? AND adjusted_score >= ? AND adjusted_score < ?
        AND outcome_200ticks IS NOT NULL AND outcome_200ticks != ''
    """, (OOS_START, lo, hi))
    row = c.fetchone()
    if row and row[0] > 0:
        wr = row[1]/row[0]*100
        print(f"  adj [{lo:.2f}-{hi:.2f}): n={row[0]:4d} WR={wr:5.1f}%")

# 5. Framework score correlation with outcome
print(f"\n=== FRAMEWORK SCORE vs WIN RATE (OOS) ===\n")
c.execute("""
    SELECT framework_scores_json, outcome_200ticks FROM signal_log 
    WHERE id >= ? AND outcome_200ticks IS NOT NULL AND outcome_200ticks != ''
    AND framework_scores_json IS NOT NULL AND framework_scores_json != ''
""", (OOS_START,))
fw_rows = c.fetchall()

fw_high_win = {}
fw_high_total = {}
fw_low_win = {}
fw_low_total = {}

for row in fw_rows:
    try:
        fw = json.loads(row[0])
        is_win = row[1] == "WIN"
        for name, score in fw.items():
            if score > 0.5:
                if name not in fw_high_win:
                    fw_high_win[name] = 0
                    fw_high_total[name] = 0
                fw_high_total[name] += 1
                if is_win:
                    fw_high_win[name] += 1
            else:
                if name not in fw_low_win:
                    fw_low_win[name] = 0
                    fw_low_total[name] = 0
                fw_low_total[name] += 1
                if is_win:
                    fw_low_win[name] += 1
    except:
        pass

print(f"{'Framework':30s} {'WR(hi)':>7s} {'WR(lo)':>7s} {'Edge':>7s} {'n_hi':>6s} {'n_lo':>6s}")
print("-" * 70)
for fw_name in sorted(set(list(fw_high_total.keys()) + list(fw_low_total.keys()))):
    wr_hi = fw_high_win.get(fw_name, 0) / fw_high_total.get(fw_name, 1) * 100
    wr_lo = fw_low_win.get(fw_name, 0) / fw_low_total.get(fw_name, 1) * 100
    edge = wr_hi - wr_lo
    n_hi = fw_high_total.get(fw_name, 0)
    n_lo = fw_low_total.get(fw_name, 0)
    if n_hi > 10 and n_lo > 10:
        print(f"{fw_name:30s} {wr_hi:6.1f}% {wr_lo:6.1f}% {edge:+6.1f}% {n_hi:5d} {n_lo:5d}")

# 6. Session analysis
print(f"\n=== SESSION vs WIN RATE (OOS, non-FLAT) ===\n")
c.execute("""
    SELECT session, COUNT(*), SUM(CASE WHEN outcome_200ticks='WIN' THEN 1 ELSE 0 END)
    FROM signal_log 
    WHERE id >= ? AND outcome_200ticks IN ('WIN', 'LOSS')
    GROUP BY session
    ORDER BY COUNT(*) DESC
""", (OOS_START,))
for row in c.fetchall():
    if row[0] and row[1] > 0:
        wr = row[2]/row[1]*100
        print(f"  {str(row[0]):15s}: n={row[1]:4d} WR={wr:5.1f}%")

# 7. Risk regime analysis
print(f"\n=== RISK REGIME vs WIN RATE (OOS, non-FLAT) ===\n")
c.execute("""
    SELECT risk_regime, COUNT(*), SUM(CASE WHEN outcome_200ticks='WIN' THEN 1 ELSE 0 END)
    FROM signal_log 
    WHERE id >= ? AND outcome_200ticks IN ('WIN', 'LOSS')
    GROUP BY risk_regime
    ORDER BY COUNT(*) DESC
""", (OOS_START,))
for row in c.fetchall():
    if row[0] and row[1] > 0:
        wr = row[2]/row[1]*100
        print(f"  {str(row[0]):15s}: n={row[1]:4d} WR={wr:5.1f}%")

conn.close()
