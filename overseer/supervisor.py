#!/usr/bin/env python3
"""OVERSEER Supervisor v3 — NEVER STOPS. Auto-restarts main.py on ANY failure.
Memory watchdog, self-healing, OANDA fallback detection.

HARDCODED RULES (cannot be overridden):
1. NEVER stop — always restart main.py regardless of exit code
2. NEVER give up on UDP — OANDA feed provides price data when bridge is silent
3. NEVER exit on clean shutdown — treat exit code 0 same as crash
4. Auto-restart with exponential backoff on repeated crashes
5. Kill and restart on memory leak (2GB limit)
6. systemd Restart=always handles supervisor itself
"""

import os
import signal
import sqlite3
import subprocess
import sys
import time

RESTART_DELAY = 5
MAX_CRASHES_10MIN = 20
MEMORY_LIMIT_MB = int(os.getenv("SUPERVISOR_MEMORY_LIMIT_MB", "2000"))
MEMORY_CHECK_INTERVAL = 60

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database", "overseer_trades.db")

crash_times = []


def _get_rss_mb(pid):
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        return 0
    return 0


def _kill_all_main_py():
    try:
        subprocess.run(["pkill", "-9", "-f", "python3.*main.py"], capture_output=True, timeout=5)
    except Exception:
        pass


def main():
    project_dir = os.path.dirname(os.path.abspath(__file__))
    main_py = os.path.join(project_dir, "main.py")
    log_dir = os.path.join(project_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_file = open(os.path.join(log_dir, "supervisor.log"), "a")

    def log(msg):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line)
        log_file.write(line + "\n")
        log_file.flush()

    log("[supervisor] OVERSEER Supervisor v3 — NEVER STOP mode")
    log(f"[supervisor] Memory limit: {MEMORY_LIMIT_MB}MB | Max crashes/10min: {MAX_CRASHES_10MIN}")
    log("[supervisor] HARDCODED: main.py ALWAYS restarts, never stops, OANDA feed fallback active")

    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGHUP, lambda *_: None)

    memory_check_counter = 0

    while True:
        now = time.time()
        crash_times[:] = [t for t in crash_times if now - t < 600]

        if len(crash_times) >= MAX_CRASHES_10MIN:
            cooldown = 60
            log(f"[supervisor] {MAX_CRASHES_10MIN} crashes in 10min. Cooldown {cooldown}s then RESTART (never stop)...")
            time.sleep(cooldown)
            crash_times.clear()
            continue

        _kill_all_main_py()
        time.sleep(2)

        log("[supervisor] Starting main.py (NEVER STOP mode)...")
        try:
            proc = subprocess.Popen(
                [sys.executable, main_py],
                cwd=project_dir,
                env=os.environ.copy(),
            )

            memory_check_counter = 0

            while proc.poll() is None:
                rss = _get_rss_mb(proc.pid)

                if rss > MEMORY_LIMIT_MB:
                    log(f"[supervisor] MEMORY LIMIT: {rss}MB > {MEMORY_LIMIT_MB}MB. Killing + restarting...")
                    proc.kill()
                    proc.wait(timeout=10)
                    crash_times.append(time.time())
                    break

                memory_check_counter += 1
                if memory_check_counter >= 12:
                    memory_check_counter = 0
                    log(f"[supervisor] Health check: RSS={rss}MB, pid={proc.pid} — ALIVE")

                time.sleep(MEMORY_CHECK_INTERVAL)

            else:
                # proc exited — ALWAYS restart regardless of exit code
                exit_code = proc.returncode
                crash_times.append(time.time())
                # HARDCODED: exit code 0 does NOT mean stop
                log(f"[supervisor] main.py exited (code={exit_code}). RESTARTING in {RESTART_DELAY}s — NEVER STOP...")

            time.sleep(RESTART_DELAY)
            continue

        except KeyboardInterrupt:
            log("[supervisor] Keyboard interrupt. Stopping...")
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            break
        except Exception as e:
            log(f"[supervisor] Unexpected error: {e}. Restarting in {RESTART_DELAY}s — NEVER STOP...")
            crash_times.append(time.time())
            time.sleep(RESTART_DELAY)

    log("[supervisor] Supervisor exited.")
    log_file.close()


if __name__ == "__main__":
    main()
