#!/usr/bin/env python3
"""
PROPHET CLI — Check Trading Status

Usage:
    python check_prophet.py
"""

import sys
import os
import sqlite3
import datetime
import psutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DB_PATH


def find_prophet_processes():
    """Find all PROPHET processes."""
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cpu_percent', 'memory_info']):
        try:
            if 'python' in proc.info['name'].lower():
                cmdline = proc.info['cmdline']
                if cmdline and 'main_deriv.py' in ' '.join(cmdline):
                    processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return processes


def get_trade_stats():
    """Get trade statistics from database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Get today's trades
        today = datetime.date.today().isoformat()
        cursor.execute("""
            SELECT result, profit
            FROM prophet_trades
            WHERE DATE(timestamp) = ?
        """, (today,))
        trades = cursor.fetchall()

        wins = sum(1 for t in trades if t[0] == "WIN")
        losses = sum(1 for t in trades if t[0] == "LOSS")
        total = len(trades)
        pnl = sum(t[1] or 0 for t in trades)
        win_rate = wins / total if total > 0 else 0

        # Get recent signals
        cursor.execute("""
            SELECT direction, reason
            FROM prophet_signals
            ORDER BY timestamp DESC
            LIMIT 5
        """)
        signals = cursor.fetchall()

        conn.close()

        return {
            'trades': total,
            'wins': wins,
            'losses': losses,
            'win_rate': win_rate,
            'pnl': pnl,
            'signals': signals
        }
    except Exception as e:
        return None


def check_prophet_status():
    """Check PROPHET trading status."""
    print("📊 PROPHET Status Check")
    print("=" * 50)

    processes = find_prophet_processes()

    if not processes:
        print("❌ PROPHET is NOT running")
        print("   Start with: prophet_cli.py start")
        return

    print(f"✅ PROPHET is running ({len(processes)} process(es))")
    print()

    for proc in processes:
        pid = proc.info['pid']
        cpu = proc.info['cpu_percent']
        mem = proc.info['memory_info']
        mem_mb = mem.rss / 1024 / 1024
        print(f"   PID: {pid}")
        print(f"   CPU: {cpu:.1f}%")
        print(f"   Memory: {mem_mb:.1f} MB")
        print()

    stats = get_trade_stats()
    if stats:
        print("📈 Today's Trading Stats:")
        print(f"   Trades: {stats['trades']}")
        print(f"   Wins: {stats['wins']}")
        print(f"   Losses: {stats['losses']}")
        print(f"   Win Rate: {stats['win_rate']:.1%}")
        print(f"   P&L: ${stats['pnl']:+.2f}")
        print()

        if stats['signals']:
            print("🔍 Recent Signals:")
            for direction, reason in stats['signals'][:3]:
                print(f"   {direction or 'NO TRADE'}: {reason[:60]}...")
            print()
    else:
        print("⚠️  No trading data available yet")
        print()

    print("💡 Use 'prophet_cli.py logs' to view detailed logs")


if __name__ == "__main__":
    check_prophet_status()
