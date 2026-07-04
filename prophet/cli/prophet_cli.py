#!/usr/bin/env python3
"""
PROPHET CLI — Unified Command Interface

Usage:
    python prophet_cli.py start    — Start PROPHET background process
    python prophet_cli.py stop     — Stop PROPHET background process
    python prophet_cli.py status   — Check PROPHET trading status
    python prophet_cli.py logs     — View PROPHET logs
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cli.start_prophet import start_prophet
from cli.stop_prophet import stop_prophet
from cli.check_prophet import check_prophet_status


def show_logs():
    log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'prophet.log')
    if not os.path.exists(log_path):
        print("No prophet.log file found yet")
        return
    with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()[-80:]
    print(''.join(lines), end='')


def print_help():
    print("""
PROPHET CLI — Unified Command Interface

Commands:
    start    — Start PROPHET background process
    stop     — Stop PROPHET background process
    status   — Check PROPHET trading status
    logs     — View PROPHET logs
    help     — Show this help message

Example:
    python prophet_cli.py start
    python prophet_cli.py status
    python prophet_cli.py stop
    """)


def main():
    if len(sys.argv) < 2:
        print_help()
        return

    command = sys.argv[1].lower()

    if command == "start":
        start_prophet()
    elif command == "stop":
        stop_prophet()
    elif command == "status":
        check_prophet_status()
    elif command == "logs":
        show_logs()
    elif command == "help":
        print_help()
    else:
        print(f"Unknown command: {command}")
        print_help()


if __name__ == "__main__":
    main()
