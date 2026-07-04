#!/usr/bin/env python3
"""
VANGUARD CLI — Stop Background Process

Usage:
    python stop_vanguard.py
"""

import sys
import os
import psutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def find_vanguard_processes():
    """Find all VANGUARD processes."""
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if 'python' in proc.info['name'].lower():
                cmdline = proc.info['cmdline']
                if cmdline and 'main_deriv.py' in ' '.join(cmdline):
                    processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return processes


def stop_vanguard():
    """Stop VANGUARD background processes."""
    print("🛑 Stopping VANGUARD...")

    processes = find_vanguard_processes()

    if not processes:
        print("✅ VANGUARD is not running")
        return

    stopped_count = 0
    for proc in processes:
        try:
            pid = proc.info['pid']
            print(f"   Stopping process {pid}...")
            proc.terminate()
            proc.wait(timeout=5)
            stopped_count += 1
        except (psutil.NoSuchProcess, psutil.TimeoutExpired, psutil.AccessDenied):
            try:
                proc.kill()
                stopped_count += 1
            except:
                pass

    print(f"✅ Stopped {stopped_count} VANGUARD process(es)")


if __name__ == "__main__":
    stop_vanguard()
