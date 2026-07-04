import sqlite3
conn = sqlite3.connect('database/overseer_trades.db')
c = conn.cursor()
c.execute("SELECT COUNT(*) FROM signal_log")
before = c.fetchone()[0]
c.execute("DELETE FROM signal_log WHERE outcome_10ticks = 'FLAT' OR outcome_10ticks IS NULL")
deleted = c.rowcount
c.execute("SELECT COUNT(*) FROM signal_log")
after = c.fetchone()[0]
conn.commit()
print(f"Before: {before:,}  Deleted: {deleted:,}  After: {after:,}")
conn.close()
