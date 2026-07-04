#!/usr/bin/env python3
"""
VANGUARD CLI — Unified Command Interface

Usage:
    python vanguard_cli.py start    — Start VANGUARD background process
    python vanguard_cli.py stop     — Stop VANGUARD background process
    python vanguard_cli.py status   — Check VANGUARD trading status
    python vanguard_cli.py logs     — View VANGUARD logs
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cli.start_vanguard import start_vanguard
from cli.stop_vanguard import stop_vanguard
from cli.check_vanguard import check_vanguard_status


def show_logs():
    log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'vanguard.log')
    if not os.path.exists(log_path):
        print("No vanguard.log file found yet")
        return
    with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()[-80:]
    print(''.join(lines), end='')


def print_help():
    print("""
VANGUARD CLI — Unified Command Interface

Commands:
    start    — Start VANGUARD background process
    stop     — Stop VANGUARD background process
    status   — Check VANGUARD trading status
    logs     — View VANGUARD logs
    help     — Show this help message

Example:
    python vanguard_cli.py start
    python vanguard_cli.py status
    python vanguard_cli.py stop
    """)


def main():
    if len(sys.argv) < 2:
        print_help()
        return

    command = sys.argv[1].lower()

    if command == "start":
        start_vanguard()
    elif command == "stop":
        stop_vanguard()
    elif command == "status":
        check_vanguard_status()
    elif command == "logs":
        show_logs()
    elif command == "help":
        print_help()
    else:
        print(f"Unknown command: {command}")
        print_help()


if __name__ == "__main__":
    main()
