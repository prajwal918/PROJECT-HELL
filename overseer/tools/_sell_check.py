import sqlite3, json

conn = sqlite3.connect("database/overseer_trades.db")

print("=== SELL Signal Outcomes (non-FLAT) ===")
cur = conn.execute("""
SELECT symbol, direction, COUNT(*) as n,
    SUM(CASE WHEN outcome_200ticks='WIN' THEN 1 ELSE 0 END) as wins,
    SUM(CASE WHEN outcome_200ticks='LOSS' THEN 1 ELSE 0 END) as losses
FROM signal_log
WHERE outcome_200ticks IS NOT NULL AND outcome_200ticks != 'FLAT' AND direction='SELL'
GROUP BY symbol ORDER BY n DESC
""")
for row in cur.fetchall():
    sym, d, n, w, l = row
    wr = w / n * 100 if n else 0
    print(f"  {sym} SELL: n={n} W={w} L={l} WR={wr:.1f}%")

print()
print("=== BUY Signal Outcomes (non-FLAT) ===")
cur2 = conn.execute("""
SELECT symbol, direction, COUNT(*) as n,
    SUM(CASE WHEN outcome_200ticks='WIN' THEN 1 ELSE 0 END) as wins
FROM signal_log
WHERE outcome_200ticks IS NOT NULL AND outcome_200ticks != 'FLAT' AND direction='BUY'
GROUP BY symbol ORDER BY n DESC
""")
for row in cur2.fetchall():
    sym, d, n, w = row
    wr = w / n * 100 if n else 0
    print(f"  {sym} BUY: n={n} W={w} WR={wr:.1f}%")

print()
print("=== Recent SELL signals (last 10) ===")
cur3 = conn.execute("""
SELECT id, symbol, score, adjusted_score, outcome_200ticks
FROM signal_log WHERE direction='SELL'
ORDER BY id DESC LIMIT 10
""")
for row in cur3.fetchall():
    print(f"  #{row[0]} {row[1]} SELL score={row[2]:.4f} adj={row[3]:.4f} outcome={row[4]}")

conn.close()
