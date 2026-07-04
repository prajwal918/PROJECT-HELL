"""Prune old tick_log data to keep DB size manageable.

Keeps last N days of tick_log (default 7). Signal_log and other
tables are preserved — only tick_log (the bulk of DB size) is pruned.
"""
import sqlite3
import os
import sys
import logging
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
LOGGER = logging.getLogger("prune_db")

DB_PATH = "/home/jogi999/Music/dfg/urlr/database/overseer_trades.db"
KEEP_DAYS = int(os.getenv("PRUNE_KEEP_DAYS", "7"))


def main():
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    cutoff_ms = now_ms - (KEEP_DAYS * 86400 * 1000)
    cutoff_dt = datetime.fromtimestamp(cutoff_ms / 1000, tz=timezone.utc)

    LOGGER.info("DB size before: %.1f GB", os.path.getsize(DB_PATH) / (1024**3))
    LOGGER.info("Pruning tick_log older than %s (keep %d days)", cutoff_dt.isoformat(), KEEP_DAYS)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")

    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM tick_log WHERE timestamp < ?", (cutoff_ms,)
        ).fetchone()[0]
    except Exception:
        LOGGER.info("Could not count rows (table too large), proceeding with delete")

    LOGGER.info("Deleting tick_log rows older than cutoff...")
    conn.execute("DELETE FROM tick_log WHERE timestamp < ?", (cutoff_ms,))
    deleted = conn.total_changes
    conn.commit()
    LOGGER.info("Deleted %d tick_log rows", deleted)

    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.commit()
    except Exception as exc:
        LOGGER.warning("WAL checkpoint failed: %s", exc)

    LOGGER.info("DB size after: %.1f GB", os.path.getsize(DB_PATH) / (1024**3))
    conn.close()


if __name__ == "__main__":
    main()
