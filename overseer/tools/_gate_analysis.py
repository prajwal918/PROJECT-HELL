"""Gate-level predictive power analysis for OVERSEER."""
import sqlite3
import json

DB = "database/overseer_trades.db"
conn = sqlite3.connect(DB)
c = conn.cursor()

OOS_START = 35761

# 1. Varying gates predictive power (ex-FLAT)
c.execute("""
    SELECT gate_states_json, outcome_200ticks FROM signal_log 
    WHERE id >= ? AND outcome_200ticks IN ('WIN', 'LOSS')
""", (OOS_START,))
rows = c.fetchall()

varying_gates = [
    "gate_A", "gate_J", "gate_Z7", "gate_H", "gate_L",
    "gate_G", "gate_T", "gate_B", "gate_SESSION", "gate_D",
    "gate_M", "gate_C", "gate_RSI", "gate_MACD", "gate_BB",
    "gate_VP", "gate_TPO", "gate_VWAP", "gate_DD", "gate_IMB",
    "gate_R", "gate_S", "gate_V", "gate_FUND",
]

print("=== VARYING GATE PREDICTIVE POWER (ex-FLAT, OOS) ===")
header = f"{'Gate':20s} {'Pass%':>6s} {'WR(P)':>6s} {'WR(F)':>6s} {'Edge':>7s} {'nP':>5s} {'nF':>5s}"
print(header)
print("-" * 60)

for target_gate in varying_gates:
    pass_win = pass_total = fail_win = fail_total = 0
    for row in rows:
        try:
            gs = json.loads(row[0])
            is_win = row[1] == "WIN"
            if gs.get(target_gate, False):
                pass_total += 1
                if is_win:
                    pass_win += 1
            else:
                fail_total += 1
                if is_win:
                    fail_win += 1
        except Exception:
            pass

    if pass_total > 5 and fail_total > 5:
        wr_p = pass_win / pass_total * 100
        wr_f = fail_win / fail_total * 100
        pr = pass_total / (pass_total + fail_total) * 100
        edge = wr_p - wr_f
        print(f"  {target_gate:18s} {pr:5.1f}% {wr_p:5.1f}% {wr_f:5.1f}% {edge:+5.1f}pp {pass_total:5d} {fail_total:5d}")
    elif pass_total > 0 or fail_total > 0:
        pr = pass_total / max(pass_total + fail_total, 1) * 100
        wr_p = pass_win / pass_total * 100 if pass_total > 0 else 0
        wr_f = fail_win / fail_total * 100 if fail_total > 0 else 0
        print(f"  {target_gate:18s} {pr:5.1f}% {wr_p:5.1f}% {wr_f:5.1f}%   (too few)")

# 2. 6BM6 BUY: what separates wins from losses?
print()
print("=== 6BM6 BUY: WIN vs LOSS GATE DIFFERENCES ===")
c.execute("""
    SELECT gate_states_json, outcome_200ticks FROM signal_log 
    WHERE id >= ? AND symbol='6BM6' AND direction='BUY'
    AND outcome_200ticks IN ('WIN', 'LOSS')
""", (OOS_START,))
bm_rows = c.fetchall()

win_gates = {}
loss_gates = {}
wins = losses = 0
for row in bm_rows:
    try:
        gs = json.loads(row[0])
        is_win = row[1] == "WIN"
        if is_win:
            wins += 1
            for g, v in gs.items():
                win_gates[g] = win_gates.get(g, 0) + (1 if v else 0)
        else:
            losses += 1
            for g, v in gs.items():
                loss_gates[g] = loss_gates.get(g, 0) + (1 if v else 0)
    except Exception:
        pass

if wins > 0 and losses > 0:
    diffs = []
    all_gates = set(list(win_gates.keys()) + list(loss_gates.keys()))
    for g in all_gates:
        wr = win_gates.get(g, 0) / wins * 100
        lr = loss_gates.get(g, 0) / losses * 100
        diff = wr - lr
        diffs.append((g, wr, lr, diff))

    diffs.sort(key=lambda x: x[3], reverse=True)
    print(f"  Wins={wins} Losses={losses}")
    header = f"  {'Gate':20s} {'Win%':>6s} {'Loss%':>6s} {'Diff':>7s}"
    print(header)
    print("  " + "-" * 45)
    for g, wr, lr, diff in diffs[:15]:
        print(f"  {g:18s} {wr:5.1f}% {lr:5.1f}% {diff:+5.1f}pp")
    print("  ...")
    for g, wr, lr, diff in diffs[-5:]:
        print(f"  {g:18s} {wr:5.1f}% {lr:5.1f}% {diff:+5.1f}pp")

# 3. 6CM6 BUY (best WR symbol)
print()
print("=== 6CM6 BUY: WIN vs LOSS GATE DIFFERENCES ===")
c.execute("""
    SELECT gate_states_json, outcome_200ticks FROM signal_log 
    WHERE id >= ? AND symbol='6CM6' AND direction='BUY'
    AND outcome_200ticks IN ('WIN', 'LOSS')
""", (OOS_START,))
cm_rows = c.fetchall()

win_gates = {}
loss_gates = {}
wins = losses = 0
for row in cm_rows:
    try:
        gs = json.loads(row[0])
        is_win = row[1] == "WIN"
        if is_win:
            wins += 1
            for g, v in gs.items():
                win_gates[g] = win_gates.get(g, 0) + (1 if v else 0)
        else:
            losses += 1
            for g, v in gs.items():
                loss_gates[g] = loss_gates.get(g, 0) + (1 if v else 0)
    except Exception:
        pass

if wins > 0 and losses > 0:
    diffs = []
    all_gates = set(list(win_gates.keys()) + list(loss_gates.keys()))
    for g in all_gates:
        wr = win_gates.get(g, 0) / wins * 100
        lr = loss_gates.get(g, 0) / losses * 100
        diff = wr - lr
        diffs.append((g, wr, lr, diff))

    diffs.sort(key=lambda x: x[3], reverse=True)
    print(f"  Wins={wins} Losses={losses}")
    header = f"  {'Gate':20s} {'Win%':>6s} {'Loss%':>6s} {'Diff':>7s}"
    print(header)
    print("  " + "-" * 45)
    for g, wr, lr, diff in diffs[:15]:
        print(f"  {g:18s} {wr:5.1f}% {lr:5.1f}% {diff:+5.1f}pp")

# 4. How many gates are trivial (always True or always False)?
print()
print("=== GATE TRIVIALITY CHECK ===")
c.execute("""
    SELECT gate_states_json FROM signal_log WHERE id >= ? LIMIT 5000
""", (OOS_START,))
all_rows = c.fetchall()
gate_stats = {}
for row in all_rows:
    try:
        gs = json.loads(row[0])
        for g, v in gs.items():
            if g not in gate_stats:
                gate_stats[g] = {"pass": 0, "total": 0}
            gate_stats[g]["total"] += 1
            if v:
                gate_stats[g]["pass"] += 1
    except Exception:
        pass

always_true = []
always_false = []
varying = []
for g, s in gate_stats.items():
    rate = s["pass"] / s["total"] * 100 if s["total"] > 0 else 0
    if rate >= 99.5:
        always_true.append(g)
    elif rate <= 0.5:
        always_false.append(g)
    else:
        varying.append((g, rate))

print(f"  Always True (>99.5%):  {len(always_true)} gates")
print(f"  Always False (<0.5%):  {len(always_false)} gates")
print(f"  Actually varying:      {len(varying)} gates")
print()
print(f"  Trivial gate list (always True): {sorted(always_true)}")
print(f"  Trivial gate list (always False): {sorted(always_false)}")
print()
print(f"  Varying gates:")
for g, rate in sorted(varying, key=lambda x: x[1]):
    print(f"    {g:25s}: {rate:5.1f}%")

conn.close()
