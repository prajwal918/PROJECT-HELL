import sqlite3, json
conn = sqlite3.connect('database/overseer_trades.db')
c = conn.cursor()
c.execute("SELECT id, symbol, tick_bid, tick_ask, framework_scores_json, outcome_10ticks, outcome_50ticks, outcome_200ticks FROM signal_log WHERE symbol='6CM6' AND outcome_200ticks IS NOT NULL ORDER BY id DESC LIMIT 5")
for r in c.fetchall():
    fw = json.loads(r[4]) if r[4] else {}
    print(f"  #{r[0]} bid={r[2]} ask={r[3]} o10={r[5]} o50={r[6]} o200={r[7]}")
c.execute("SELECT MIN(tick_bid), MAX(tick_bid), MIN(tick_ask), MAX(tick_ask) FROM signal_log WHERE symbol='6CM6' AND outcome_200ticks IS NOT NULL")
r = c.fetchone()
print(f"\n6CM6 price range: bid=[{r[0]}, {r[1]}] ask=[{r[2]}, {r[3]}]")
price_range = (r[1] or 0) - (r[0] or 0)
print(f"Price range (bid): {price_range:.10f}")
print(f"In pips (pip_size=0.0001): {price_range/0.0001:.1f}")
conn.close()
