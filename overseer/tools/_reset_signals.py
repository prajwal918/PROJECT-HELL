import sqlite3
conn = sqlite3.connect('database/overseer_trades.db')
c = conn.cursor()
c.execute("DELETE FROM signal_log")
print(f"Deleted {c.rowcount:,} old signals")
conn.commit()
conn.close()
