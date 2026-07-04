#!/usr/bin/env python3
"""
VANGUARD CLI — Start Background Process

Usage:
    python start_vanguard.py
"""

import sys
import os
import subprocess
import psutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import MAX_MEMORY_MB, MAX_CPU_PERCENT


def is_vanguard_running():
    """Check if VANGUARD process is already running."""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if 'python' in proc.info['name'].lower():
                cmdline = proc.info['cmdline']
                if cmdline and 'main_deriv.py' in ' '.join(cmdline):
                    return True, proc.info['pid']
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False, None


def start_vanguard():
    """Start VANGUARD in background with resource limits."""
    print("🚀 Starting VANGUARD...")

    running, pid = is_vanguard_running()
    if running:
        print(f"⚠️  VANGUARD is already running (PID: {pid})")
        print("Use 'vanguard_cli.py stop' to stop it first.")
        return

    try:
        # Start main_deriv.py in background
        script_path = os.path.join(os.path.dirname(__file__), '..', 'main_deriv.py')

        if not os.path.exists(script_path):
            print(f"❌ Error: main_deriv.py not found at {script_path}")
            return

        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_path = os.path.join(project_dir, 'vanguard.log')

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
            # Give maximum priority to VANGUARD for HFT speed
            if hasattr(p, 'nice'):
                p.nice(-10)  # High priority (requires sudo, but will just ignore if unprivileged)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        print(f"✅ VANGUARD started successfully (PID: {process.pid})")
        print(f"   Running with UNLIMITED RESOURCES (HFT Mode)")
        print("   Use 'vanguard_cli.py status' to check status")
        print("   Use 'vanguard_cli.py logs' to view logs")

    except Exception as e:
        print(f"❌ Failed to start VANGUARD: {e}")


if __name__ == "__main__":
    start_vanguard()
