#!/usr/bin/env python3
"""
OVERSEER v14 — LEGENDARY DASHBOARD (curses)
Full keyboard control. Works in any Linux terminal.
"""

import curses
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

PRJ = Path(__file__).resolve().parent
DB = PRJ / "database" / "overseer_trades.db"
ENV = PRJ / ".env"
LOG = PRJ / "logs" / "overseer.log"

def env_get(k, d=""):
    try:
        with open(ENV) as f:
            for ln in f:
                if ln.strip().startswith(f"{k}="):
                    return ln.strip().split("=", 1)[1]
    except: pass
    return d

def env_set(k, v):
    lines, found = [], False
    try:
        with open(ENV) as f:
            for ln in f:
                if ln.strip().startswith(f"{k}="):
                    lines.append(f"{k}={v}\n"); found = True
                else: lines.append(ln)
    except: lines = [f"{k}={v}\n"]; found = True
    if not found: lines.append(f"{k}={v}\n")
    with open(ENV, "w") as f: f.writelines(lines)

def running(p):
    try:
        r = subprocess.run(["pgrep", "-f", p], capture_output=True, timeout=3)
        return r.returncode == 0
    except: return False

def rss_mb():
    try:
        r = subprocess.run(["pgrep", "-f", "python3.*main.py"], capture_output=True, text=True, timeout=3)
        if r.returncode == 0 and r.stdout.strip():
            pid = int(r.stdout.strip().split("\n")[0])
            with open(f"/proc/{pid}/status") as f:
                for ln in f:
                    if ln.startswith("VmRSS:"):
                        return int(ln.split()[1]) // 1024
    except: pass
    return 0

def start_sys():
    subprocess.Popen(["sudo", sys.executable, str(PRJ/"supervisor.py")],
                     cwd=str(PRJ), start_new_session=True,
                     stdout=open(PRJ/"logs"/"supervisor_console.log", "a"),
                     stderr=subprocess.STDOUT)

def stop_sys():
    try:
        subprocess.run(["sudo", "pkill", "-9", "-f", "python3.*supervisor.py"], capture_output=True, timeout=3)
    except: pass
    try:
        subprocess.run(["sudo", "pkill", "-9", "-f", "python3.*main.py"], capture_output=True, timeout=3)
    except: pass

def restart_sys():
    stop_sys(); time.sleep(2); start_sys()

def apply_wr(pct):
    t = {80:"0.80",85:"0.85",90:"0.92",95:"0.95",99:"0.99"}[pct]
    env_set("QUALITY_SCORE_MIN", t)
    for s in ["6BM6","6JM6","6AM6","6CM6","6EM6"]:
        env_set(f"THRESH_{s}", t)
    env_set("LEGENDARY_MODE_ENABLED", "true" if pct>=90 else "false")
    env_set("LEGENDARY_KELLY_FRACTION", "0.75" if pct>=95 else "0.50" if pct>=90 else "0.25")
    env_set("AUTO_EXECUTE", "true")
    env_set("MT5_ENABLED", "false")
    env_set("OANDA_FEED_ENABLED", "true")
    restart_sys()

def db_stats():
    try:
        c = sqlite3.connect(str(DB), timeout=5)
        d = {
            "ticks": c.execute("SELECT COUNT(*) FROM tick_log").fetchone()[0],
            "sigs": c.execute("SELECT COUNT(*) FROM signal_log").fetchone()[0],
        }
        try:
            d["trades"] = c.execute("SELECT COUNT(*) FROM trade_executions WHERE exit_price IS NOT NULL").fetchone()[0]
            d["wins"] = c.execute("SELECT COUNT(*) FROM trade_executions WHERE pnl>0 AND exit_price IS NOT NULL").fetchone()[0]
            d["losses"] = c.execute("SELECT COUNT(*) FROM trade_executions WHERE pnl<0 AND exit_price IS NOT NULL").fetchone()[0]
            d["pnl"] = c.execute("SELECT COALESCE(SUM(pnl),0) FROM trade_executions WHERE exit_price IS NOT NULL").fetchone()[0]
        except: d["trades"]=d["wins"]=d["losses"]=0; d["pnl"]=0
        try:
            d["srows"] = c.execute("SELECT symbol,direction,score,adjusted_score,timestamp FROM signal_log ORDER BY id DESC LIMIT 12").fetchall()
        except: d["srows"] = []
        try:
            d["trows"] = c.execute("SELECT symbol,direction,pnl,timestamp FROM trade_executions WHERE exit_price IS NOT NULL ORDER BY trade_id DESC LIMIT 12").fetchall()
        except: d["trows"] = []
        c.close()
        return d
    except Exception:
        return {"ticks":0,"sigs":0,"trades":0,"wins":0,"losses":0,"pnl":0,"srows":[],"trows":[]}

def last_score():
    try:
        r = subprocess.run(["grep","SCORE_DEBUG",str(LOG)], capture_output=True, text=True, timeout=3)
        if r.stdout.strip():
            return r.stdout.strip().split("\n")[-1][-80:]
    except: pass
    return "No scores yet"

def last_signal():
    try:
        r = subprocess.run(["grep","SIGNAL_STRENGTH",str(LOG)], capture_output=True, text=True, timeout=3)
        if r.stdout.strip():
            return r.stdout.strip().split("\n")[-1][-80:]
    except: pass
    return "No signals above threshold"

class Dashboard:
    def __init__(self, stdscr):
        self.s = stdscr
        self.h, self.w = self.s.getmaxyx()
        curses.curs_set(0)
        curses.start_color()
        curses.use_default_colors()
        for i in range(1, 8):
            curses.init_pair(i, i, -1)
        curses.init_pair(8, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(9, curses.COLOR_BLACK, curses.COLOR_GREEN)
        curses.init_pair(10, curses.COLOR_BLACK, curses.COLOR_RED)
        self.tab = 0
        self.msg = ""
        self.msg_time = 0

    def show_msg(self, m):
        self.msg = m
        self.msg_time = time.time()

    def draw(self):
        self.s.clear()
        h, w = self.h, self.w
        y = 0

        # Header
        self.s.addstr(y, 0, " OVERSEER v14 - LEGENDARY DASHBOARD ", curses.color_pair(8) | curses.A_BOLD)
        y += 1

        # Status line
        mr = running("python3.*main.py")
        sr = running("python3.*supervisor.py")
        rss = rss_mb()
        st = "RUNNING" if mr else "STOPPED"
        cp = 2 if mr else 1
        self.s.addstr(y, 0, f" System: ", curses.A_BOLD)
        self.s.addstr(y, 10, f"{st}", curses.color_pair(cp) | curses.A_BOLD)
        self.s.addstr(y, 20, f" Supervisor: {'ON' if sr else 'OFF'}  RAM: {rss}MB", curses.A_BOLD)
        y += 1

        # Settings line
        thr = env_get("QUALITY_SCORE_MIN", "?")
        leg = env_get("LEGENDARY_MODE_ENABLED", "?")
        aex = env_get("AUTO_EXECUTE", "?")
        self.s.addstr(y, 0, f" Thr: ", curses.A_BOLD)
        self.s.addstr(y, 6, f"{thr}", curses.color_pair(4) | curses.A_BOLD)
        self.s.addstr(y, 15, f" Leg: {leg}  Auto: {aex}", curses.A_BOLD)
        y += 1

        # DB stats line
        db = db_stats()
        wr = db["wins"] / max(db["wins"]+db["losses"],1)*100
        pnl_c = 2 if db["pnl"]<0 else 3
        self.s.addstr(y, 0, f" Ticks: {db['ticks']:,}  Sigs: {db['sigs']:,}  Trades: {db['trades']}  "
                     f"WR: {wr:.1f}%  P&L: ", curses.A_BOLD)
        self.s.addstr(y, w-12, f"${db['pnl']:.2f}", curses.color_pair(pnl_c) | curses.A_BOLD)
        y += 1

        # Score/Signal lines
        sc = last_score()[:w-10]
        self.s.addstr(y, 0, f" Score: ", curses.A_BOLD)
        self.s.addstr(y, 8, f"{sc}", curses.color_pair(6))
        y += 1
        sig = last_signal()[:w-10]
        self.s.addstr(y, 0, f" Signal: ", curses.A_BOLD)
        self.s.addstr(y, 9, f"{sig}", curses.color_pair(4))
        y += 1

        # Separator
        if y < h-1:
            self.s.addstr(y, 0, " " + "=" * (w-2), curses.color_pair(7))
            y += 1

        # Win rate buttons
        if y < h-1:
            btns = [("1:80%",2),("2:85%",5),("3:90%",6),("4:95%",1),("5:99%",3)]
            x = 2
            for txt, clr in btns:
                self.s.addstr(y, x, f"[{txt}]", curses.color_pair(clr) | curses.A_BOLD)
                x += len(txt) + 2
            x += 2
            self.s.addstr(y, x, "[S]tart", curses.color_pair(2) | curses.A_BOLD); x+=9
            self.s.addstr(y, x, "[X]top", curses.color_pair(1) | curses.A_BOLD); x+=8
            self.s.addstr(y, x, "[R]estart", curses.color_pair(4) | curses.A_BOLD); x+=10
            self.s.addstr(y, x, "[Q]uit", curses.color_pair(1) | curses.A_BOLD)
            y += 1

        # Separator
        if y < h-1:
            self.s.addstr(y, 0, " " + "=" * (w-2), curses.color_pair(7))
            y += 1

        # Table headers
        if y < h-1:
            self.s.addstr(y, 2, " Symbol Dir  Score      Adj        Time", curses.color_pair(8) | curses.A_BOLD)
            y += 1

        # Signals table
        for r in (db.get("srows") or []):
            if y >= h-2: break
            sym = str(r[0])[:6]
            d = str(r[1])[:3]
            sc = f"{r[2]:.4f}" if r[2] else "?"
            adj = f"{r[3]:.4f}" if r[3] else "?"
            ts = str(r[4])[:19] if r[4] else "?"
            self.s.addstr(y, 2, f" {sym:<6} {d:<3} {sc:<8} {adj:<10} {ts}")
            y += 1

        # Message line at bottom
        if self.msg and time.time()-self.msg_time < 5:
            self.s.addstr(h-2, 2, f" {self.msg} ", curses.color_pair(9) | curses.A_BOLD)

        self.s.refresh()

    def run(self):
        while True:
            try:
                self.draw()
                k = self.s.getch()
            except KeyboardInterrupt:
                break
            except: continue

            if k in (ord('q'), ord('Q')):
                break
            elif k in (ord('s'), ord('S')):
                start_sys(); self.show_msg("SYSTEM STARTED")
            elif k in (ord('x'), ord('X')):
                stop_sys(); self.show_msg("SYSTEM STOPPED")
            elif k in (ord('d'), ord('D')):
                restart_sys(); self.show_msg("SYSTEM RESTARTED")
            elif k == ord('r'):
                self.show_msg("REFRESHED")
            elif k == ord('1'):
                apply_wr(80); self.show_msg("WIN RATE = 80% - RESTARTING...")
            elif k == ord('2'):
                apply_wr(85); self.show_msg("WIN RATE = 85% - RESTARTING...")
            elif k == ord('3'):
                apply_wr(90); self.show_msg("WIN RATE = 90% - RESTARTING...")
            elif k == ord('4'):
                apply_wr(95); self.show_msg("WIN RATE = 95% - RESTARTING...")
            elif k == ord('5'):
                apply_wr(99); self.show_msg("WIN RATE = 99% - RESTARTING...")

def main(stdscr):
    dash = Dashboard(stdscr)
    dash.run()

if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
