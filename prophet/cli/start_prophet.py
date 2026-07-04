#!/usr/bin/env python3
"""
PROPHET CLI — Start Background Process

Usage:
    python start_prophet.py
"""

import sys
import os
import subprocess
import psutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import MAX_MEMORY_MB, MAX_CPU_PERCENT


def is_prophet_running():
    """Check if PROPHET process is already running."""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if 'python' in proc.info['name'].lower():
                cmdline = proc.info['cmdline']
                if cmdline and 'main_deriv.py' in ' '.join(cmdline):
                    return True, proc.info['pid']
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False, None


def start_prophet():
    """Start PROPHET in background with resource limits."""
    print("🚀 Starting PROPHET...")

    running, pid = is_prophet_running()
    if running:
        print(f"⚠️  PROPHET is already running (PID: {pid})")
        print("Use 'prophet_cli.py stop' to stop it first.")
        return

    try:
        # Start main_deriv.py in background
        script_path = os.path.join(os.path.dirname(__file__), '..', 'main_deriv.py')

        if not os.path.exists(script_path):
            print(f"❌ Error: main_deriv.py not found at {script_path}")
            return

        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_path = os.path.join(project_dir, 'prophet.log')

        # Create process with resource limits. Keep cwd in the project so .env/db/log paths resolve correctly.
        log_file = open(log_path, 'a', encoding='utf-8')
        process = subprocess.Popen(
            [sys.executable, script_path],
            cwd=project_dir,
            stdout=log_file,
            stderr=log_file,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,
            start_new_session=(os.name != 'nt'),
            close_fds=(os.name != 'nt'),
        )

        # Set resource limits
        try:
            p = psutil.Process(process.pid)
            # Give maximum priority to PROPHET for HFT speed
            if hasattr(p, 'nice'):
                p.nice(-10)  # High priority (requires sudo, but will just ignore if unprivileged)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        print(f"✅ PROPHET started successfully (PID: {process.pid})")
        print(f"   Running with UNLIMITED RESOURCES (HFT Mode)")
        print("   Use 'prophet_cli.py status' to check status")
        print("   Use 'prophet_cli.py logs' to view logs")

    except Exception as e:
        print(f"❌ Failed to start PROPHET: {e}")


if __name__ == "__main__":
    start_prophet()
