import sqlite3
conn = sqlite3.connect('database/overseer_trades.db')
c = conn.cursor()
c.execute("UPDATE signal_log SET outcome_10ticks = NULL, outcome_50ticks = NULL, outcome_200ticks = NULL WHERE outcome_10ticks = 'FLAT' AND outcome_50ticks = 'FLAT' AND outcome_200ticks = 'FLAT'")
print(f"Reset {c.rowcount} old FLAT outcomes to NULL")
conn.commit()
conn.close()
