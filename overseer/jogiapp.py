"""
jogiapp - searchable local launcher for OVERSEER.

Runs a small browser-based control app using only the Python standard library.
Use it to start/stop main.py while keeping APIs, dashboard,
database logging, gates, scoring, and MotiveWave ingest enabled.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "overseer.log"
PID_FILE = LOG_DIR / "jogiapp.pid"
STDOUT_FILE = LOG_DIR / "jogiapp_stdout.log"
STDERR_FILE = LOG_DIR / "jogiapp_stderr.log"
ENV_FILE = ROOT / ".env"

HOST = "127.0.0.1"
PORT = 8787
APP_URL = f"http://{HOST}:{PORT}"
DASHBOARD_URL = "http://localhost:8080"


def python_executable() -> str:
    candidate = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if candidate.exists():
        return str(candidate)
    return sys.executable or ("python" if os.name == "nt" else "python3")


def read_pid() -> int | None:
    try:
        text = PID_FILE.read_text(encoding="utf-8").strip()
        return int(text) if text else None
    except (OSError, ValueError):
        return None


def discover_main_pid() -> int | None:
    if os.name == "nt":
        script = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.CommandLine -match 'main.py' -and $_.CommandLine -notmatch 'jogiapp.py' } | "
            "Select-Object -First 1 -ExpandProperty ProcessId"
        )
        cmd = ["powershell", "-NoProfile", "-Command", script]
    else:
        cmd = ["pgrep", "-f", "python.*main.py"]
    try:
        result = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, timeout=2, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None

    for line in result.stdout.splitlines():
        try:
            pid = int(line.strip())
        except ValueError:
            continue
        if pid != os.getpid():
            return pid
    return None


def is_pid_running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def get_env_settings() -> dict:
    if not ENV_FILE.exists():
        return {}
    settings = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            settings[k.strip()] = v.strip()
    return settings


def update_env_settings(updates: dict) -> None:
    if not ENV_FILE.exists():
        ENV_FILE.touch()
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    out = []
    seen = set()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            out.append(line)
            continue
        if "=" in line:
            k, _ = line.split("=", 1)
            k = k.strip()
            if k in updates:
                out.append(f"{k}={updates[k]}")
                seen.add(k)
            else:
                out.append(line)
        else:
            out.append(line)
    
    for k, v in updates.items():
        if k not in seen:
            out.append(f"{k}={v}")
    
    ENV_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")


def start_overseer() -> dict[str, object]:
    LOG_DIR.mkdir(exist_ok=True)
    pid = read_pid()
    if is_pid_running(pid):
        return {"ok": False, "message": f"Already running as PID {pid}.", "pid": pid}
    discovered_pid = discover_main_pid()
    if is_pid_running(discovered_pid):
        PID_FILE.write_text(str(discovered_pid), encoding="utf-8")
        return {"ok": False, "message": f"OVERSEER is already running as PID {discovered_pid}.", "pid": discovered_pid}
    if log_looks_live():
        return {
            "ok": False,
            "message": "OVERSEER already appears to be running from another launcher.",
            "pid": None,
        }

    stdout = STDOUT_FILE.open("ab")
    stderr = STDERR_FILE.open("ab")
    kwargs: dict[str, object] = {
        "cwd": str(ROOT),
        "stdin": subprocess.DEVNULL,
        "stdout": stdout,
        "stderr": stderr,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True

    proc = subprocess.Popen([python_executable(), "main.py"], **kwargs)
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    return {"ok": True, "message": "Started OVERSEER kernel.", "pid": proc.pid}


def stop_overseer() -> dict[str, object]:
    pid = read_pid()
    if not is_pid_running(pid):
        # try discover it
        discovered = discover_main_pid()
        if discovered:
            pid = discovered
        else:
            try:
                PID_FILE.unlink()
            except OSError:
                pass
            return {"ok": False, "message": "No running OVERSEER process found.", "pid": None}

    assert pid is not None
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False)
    else:
        try:
            os.killpg(pid, signal.SIGTERM)
        except OSError:
            os.kill(pid, signal.SIGTERM)

    deadline = time.time() + 8
    while time.time() < deadline and is_pid_running(pid):
        time.sleep(0.25)

    try:
        PID_FILE.unlink()
    except OSError:
        pass
    return {"ok": True, "message": f"Stopped PID {pid}.", "pid": pid}


def tail_log(max_bytes: int = 18000) -> str:
    if not LOG_FILE.exists():
        return "No logs/overseer.log yet."
    with LOG_FILE.open("rb") as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        fh.seek(max(0, size - max_bytes))
        return fh.read().decode("utf-8", errors="replace")


def latest_tick_line() -> str:
    for line in reversed(tail_log(12000).splitlines()):
        if "Ticks:" in line:
            return line
    return ""


def latest_tick_age_seconds() -> float | None:
    line = latest_tick_line()
    if len(line) < 19:
        return None
    try:
        ts = datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return max(0.0, time.time() - ts.timestamp())


def latest_signal_line() -> str:
    for line in reversed(tail_log(24000).splitlines()):
        if "[SIGNAL_STRENGTH]" in line:
            return line.split("[SIGNAL_STRENGTH]")[-1].strip()
    return "Awaiting orderflow data..."


def get_orderflow_dashboard() -> dict:
    path = LOG_DIR / "orderflow_dashboard.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_rejections() -> list:
    path = LOG_DIR / "overseer.log"
    if not path.exists():
        return []
    rejections = []
    try:
        lines = tail_log(48000).splitlines()
        for line in reversed(lines):
            if "[REJECTION]" in line:
                parts = line.split("[REJECTION]")[-1].strip().split(" | ")
                if len(parts) >= 4:
                    sym_dir = parts[0].split(" ")
                    rejections.append({
                        "symbol": sym_dir[0],
                        "direction": sym_dir[1],
                        "score": parts[1].replace("Score: ", ""),
                        "required": parts[2].replace("Threshold: ", ""),
                        "reason": parts[3].replace("Reason: ", "")
                    })
                    if len(rejections) >= 10: break
    except Exception:
        pass
    return rejections


def log_looks_live(max_age_seconds: int = 20) -> bool:
    age = latest_tick_age_seconds()
    return age is not None and age <= max_age_seconds


def status() -> dict[str, object]:
    pid = read_pid()
    if not is_pid_running(pid):
        discovered_pid = discover_main_pid()
        if is_pid_running(discovered_pid):
            pid = discovered_pid
            try:
                PID_FILE.write_text(str(pid), encoding="utf-8")
            except OSError:
                pass
    pid_running = is_pid_running(pid)
    external_running = not pid_running and log_looks_live()
    running = pid_running or external_running
    env = get_env_settings()
    mode = "Auto-Trade" if env.get("AUTO_EXECUTE", "").lower() == "true" else "Signal-Only"
    return {
        "running": running,
        "pid": pid if pid_running else None,
        "external": external_running,
        "mode": mode,
        "dashboard": DASHBOARD_URL,
        "latest_tick": latest_tick_line(),
        "latest_signal": latest_signal_line(),
        "orderflow_dashboard": get_orderflow_dashboard(),
        "rejections": get_rejections(),
        "settings": env,
    }


HTML = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>jogiapp KERNEL</title>
  <style>
    :root { color-scheme: dark; font-family: Segoe UI, Inter, Arial, sans-serif; }
    body { margin: 0; background: #0f1418; color: #e8eef2; }
    header { display: flex; align-items: center; justify-content: space-between; padding: 18px 22px; border-bottom: 1px solid #26313a; }
    h1 { margin: 0; font-size: 26px; letter-spacing: 0; }
    main { padding: 18px 22px 24px; }
    .status { color: #9db2c3; font-size: 14px; }
    .bar { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 16px; align-items: center; }
    button, a.button { border: 1px solid #344653; background: #18232b; color: #e8eef2; padding: 11px 15px; border-radius: 6px; cursor: pointer; text-decoration: none; font-size: 14px; }
    button.primary { background: #1f6f54; border-color: #2f906f; }
    button.danger { background: #7b2d34; border-color: #a2414b; }
    button.active { border-color: #00ffaa; box-shadow: 0 0 5px #00ffaa; }
    button:hover, a.button:hover { filter: brightness(1.12); }
    .panel { border: 1px solid #26313a; border-radius: 6px; background: #111a20; margin-bottom: 16px; }
    .panel .row { padding: 12px 14px; border-bottom: 1px solid #26313a; }
    .panel .row:last-child { border-bottom: 0; }
    .label { color: #8fa5b7; display: inline-block; width: 140px; }
    .signal-text { font-family: Consolas, monospace; color: #00ffaa; font-weight: bold; }
    pre { margin: 0; white-space: pre-wrap; word-break: break-word; font: 12px/1.45 Consolas, ui-monospace, SFMono-Regular, monospace; background: #080c0f; border: 1px solid #26313a; border-radius: 6px; padding: 14px; min-height: 200px; max-height: 400px; overflow: auto; }
    input[type="text"] { background: #080c0f; border: 1px solid #26313a; color: #e8eef2; padding: 6px 8px; border-radius: 4px; width: 180px; }
    .tab-bar { display: flex; gap: 20px; border-bottom: 1px solid #26313a; margin-bottom: 16px; }
    .tab { padding: 10px 4px; cursor: pointer; color: #8fa5b7; border-bottom: 2px solid transparent; }
    .tab.active { color: #e8eef2; border-bottom: 2px solid #00ffaa; }
  </style>
</head>
<body>
  <header>
    <h1>jogiapp KERNEL</h1>
    <div class="status" id="topStatus">Loading...</div>
  </header>
  <main>
    <div class="tab-bar">
      <div class="tab active" onclick="showTab('dashboard')">Dashboard</div>
      <div class="tab" onclick="showTab('settings')">Settings & Potential</div>
      <div class="tab" onclick="showTab('logview')">Kernel Logs</div>
    </div>

    <div id="tab-dashboard">
      <div class="bar">
        <button class="primary" id="btnMainStart" onclick="start()">Run Kernel</button>
        <button class="danger" id="btnMainStop" onclick="stop()">Stop Kernel</button>
        <button onclick="refresh()">Refresh Now</button>
        <a class="button" href="http://localhost:8080" target="_blank">Full AI Analytics Dashboard</a>
      </div>
      
      <section class="panel">
        <div class="row"><span class="label">Kernel Mode</span><span id="mode" style="font-weight:bold;">-</span></div>
        <div class="row"><span class="label">Process ID</span><span id="process">-</span></div>
        <div class="row"><span class="label">Latest Tick</span><span id="tick">-</span></div>
        <div class="row"><span class="label">Last Signal</span><span id="signal" class="signal-text">-</span></div>
      </section>

      <section class="panel">
        <div class="row" style="background: #a2414b; color: white;"><strong>Live System Arming Control</strong></div>
        <div class="row bar" style="padding: 12px 14px; margin-bottom: 0;">
          <button class="danger" onclick="stop()">EMERGENCY KILL</button>
          <button style="background: #ffcc00; color: black;" onclick="flatten()">FLATTEN ALL POSITIONS</button>
          <button class="primary" onclick="start()">RE-ARM SYSTEM</button>
          <span id="riskHaltStatus" style="margin-left: auto; font-weight: bold; color: #00ffaa;">SYSTEM ARMED</span>
        </div>
      </section>

      <section class="panel">
        <div class="row" style="background: #1f6f54; color: white;"><strong>Order Flow Sentiment Matrix</strong></div>
        <div class="row" style="padding: 0; overflow-x: auto;">
          <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 12px;">
            <thead>
              <tr style="background: #18232b; color: #8fa5b7; border-bottom: 1px solid #26313a;">
                <th style="padding: 8px;">Symbol</th>
                <th style="padding: 8px;">Combined</th>
                <th style="padding: 8px;">CVD</th>
                <th style="padding: 8px;">Spoofing</th>
                <th style="padding: 8px;">Absorption</th>
                <th style="padding: 8px;">HFT</th>
                <th style="padding: 8px;">Vacuum</th>
                <th style="padding: 8px;">Iceberg</th>
                <th style="padding: 8px;">Adverse</th>
                <th style="padding: 8px;">Divergence</th>
              </tr>
            </thead>
            <tbody id="ofBody">
              <tr><td colspan="10" style="padding: 20px; text-align: center; color: #555;">Waiting for ticks...</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="panel">
        <div class="row" style="background: #18232b;"><strong>Rejection Journal</strong></div>
        <div class="row" style="padding: 0;">
          <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 11px; color: #9db2c3;">
            <thead>
              <tr style="background: #080c0f; border-bottom: 1px solid #26313a;">
                <th style="padding: 6px;">Sym</th>
                <th style="padding: 6px;">Dir</th>
                <th style="padding: 6px;">Score</th>
                <th style="padding: 6px;">Thresh</th>
                <th style="padding: 6px;">Rejection Reason</th>
              </tr>
            </thead>
            <tbody id="rejectionBody"></tbody>
          </table>
        </div>
      </section>
    </div>

    <div id="tab-settings" style="display:none;">
      <section class="panel">
        <div class="row" style="background: #18232b; display: flex; justify-content: space-between; align-items: center;">
          <strong>Potential & Adjustment Control (Kernel Level)</strong>
          <button class="primary" onclick="saveSettings()">Save & Apply Changes</button>
        </div>
        <div id="settingsContainer">
          <div class="row" style="padding: 20px; text-align: center;">Loading .env parameters...</div>
        </div>
      </section>
    </div>

    <div id="tab-logview" style="display:none;">
      <pre id="log">Loading log...</pre>
    </div>

  </main>
  <script>
    let currentSettings = {};

    function showTab(name) {
      ['dashboard', 'settings', 'logview'].forEach(t => {
        document.getElementById('tab-' + t).style.display = (t === name ? 'block' : 'none');
      });
      document.querySelectorAll('.tab').forEach(el => {
        el.classList.toggle('active', el.textContent.toLowerCase().includes(name));
      });
      if (name === 'settings') loadSettings();
    }

    async function api(path, method='GET', body=null) {
      const opts = { method };
      if (body) {
        opts.body = JSON.stringify(body);
        opts.headers = { 'Content-Type': 'application/json' };
      }
      const response = await fetch(path, opts);
      return await response.json();
    }

    async function start() { const r = await api('/api/start', 'POST'); await refresh(); if (!r.ok) alert(r.message); }
    async function stop() { const r = await api('/api/stop', 'POST'); await refresh(); if (!r.ok) alert(r.message); }
    async function flatten() { if (confirm("Flatten all open positions?")) { await api('/api/flatten', 'POST'); alert("Flatten signal sent."); } }

    async function loadSettings() {
      const s = await api('/api/settings');
      currentSettings = s;
      const container = document.getElementById('settingsContainer');
      const keys = Object.keys(s).sort();
      let html = '';
      
      // Categorize common ones
      const common = ["QUALITY_SCORE_MIN", "AUTO_EXECUTE", "MIN_RR_RATIO", "GATE_B_MIN_PASS", "MAX_DAILY_TRADES"];
      
      html += '<div class="row" style="background: #080c0f; font-weight: bold;">Core Risk & Execution</div>';
      for (const k of common) {
        if (s[k] !== undefined) {
           html += `<div class="row"><span class="label">${k}</span><input type="text" id="set_${k}" value="${s[k]}"></div>`;
        }
      }

      html += '<div class="row" style="background: #080c0f; font-weight: bold;">Pair Specific Thresholds</div>';
      for (const k of keys) {
        if (k.startsWith("THRESH_")) {
           html += `<div class="row"><span class="label">${k}</span><input type="text" id="set_${k}" value="${s[k]}"></div>`;
        }
      }

      html += '<div class="row" style="background: #080c0f; font-weight: bold;">Other Parameters</div>';
      for (const k of keys) {
        if (!common.includes(k) && !k.startsWith("THRESH_") && !k.includes("KEY") && !k.includes("PASSWORD")) {
           html += `<div class="row"><span class="label">${k}</span><input type="text" id="set_${k}" value="${s[k]}"></div>`;
        }
      }
      container.innerHTML = html;
    }

    async function saveSettings() {
      const updates = {};
      const inputs = document.querySelectorAll('#settingsContainer input');
      inputs.forEach(inp => {
        const key = inp.id.replace('set_', '');
        updates[key] = inp.value;
      });
      const r = await api('/api/settings', 'POST', updates);
      alert(r.message);
      if (confirm("Would you like to restart the kernel now to apply changes?")) {
          await stop();
          await start();
      }
    }

    async function refresh() {
      const s = await api('/api/status');
      document.getElementById('topStatus').textContent = s.running ? 'Running' : 'Stopped';
      document.getElementById('mode').textContent = s.mode;
      document.getElementById('process').textContent = s.running ? (s.pid ? `PID ${s.pid}` : 'Running External') : 'Stopped';
      document.getElementById('tick').textContent = s.latest_tick || '-';
      document.getElementById('signal').textContent = s.latest_signal || '-';
      
      const rBody = document.getElementById('rejectionBody');
      if (s.rejections && s.rejections.length > 0) {
          rBody.innerHTML = s.rejections.map(r => `
            <tr style="border-bottom: 1px solid #26313a;">
              <td style="padding: 6px;">${r.symbol}</td>
              <td style="padding: 6px; color: ${r.direction === 'BUY' ? '#00ffaa' : '#ff4466'};">${r.direction}</td>
              <td style="padding: 6px;">${r.score}</td>
              <td style="padding: 6px;">${r.required}</td>
              <td style="padding: 6px; color: #8fa5b7;">${r.reason}</td>
            </tr>
          `).join('');
      }

      const ofBody = document.getElementById('ofBody');
      const ofData = s.orderflow_dashboard || {};
      const symbols = Object.keys(ofData).sort();
      if (symbols.length > 0) {
        let h = '';
        for (const sym of symbols) {
          const d = ofData[sym];
          const getC = (v) => {
            if (!v) return '#8b949e';
            if (v.includes('STRONG BUY')) return '#00ffaa';
            if (v.includes('BUY')) return '#00aa77';
            if (v.includes('STRONG SELL')) return '#ff4466';
            if (v.includes('SELL')) return '#aa3344';
            if (v === 'PASS') return '#00ffaa';
            if (v === 'SAFE') return '#00ffaa';
            if (v === 'RISK') return '#ff4466';
            if (v === 'DIVERGENCE') return '#ffcc00';
            return '#8b949e';
          };
          h += `<tr style="border-bottom: 1px solid #26313a;">
            <td style="padding: 8px; font-weight: bold;">${sym}</td>
            <td style="padding: 8px; color: ${getC(d.combined)}; font-weight: bold;">${d.combined}</td>
            <td style="padding: 8px; color: ${getC(d.cvd)};">${d.cvd}</td>
            <td style="padding: 8px; color: ${getC(d.spoof)};">${d.spoof}</td>
            <td style="padding: 8px; color: ${getC(d.absorption)};">${d.absorption}</td>
            <td style="padding: 8px; color: ${getC(d.hft)};">${d.hft}</td>
            <td style="padding: 8px; color: ${getC(d.vacuum)};">${d.vacuum}</td>
            <td style="padding: 8px; color: ${getC(d.iceberg)};">${d.iceberg}</td>
            <td style="padding: 8px; color: ${getC(d.adverse)}; font-weight: bold;">${d.adverse}</td>
            <td style="padding: 8px; color: ${getC(d.divergence)};">${d.divergence}</td>
          </tr>`;
        }
        ofBody.innerHTML = h;
      }

      const log = await fetch('/api/log').then(r => r.text());
      const el = document.getElementById('log');
      if (el) {
          el.textContent = log;
          if (document.getElementById('tab-logview').style.display !== 'none') {
             el.scrollTop = el.scrollHeight;
          }
      }
    }
    refresh();
    setInterval(refresh, 3000);
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, data: dict[str, object]) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/status":
            self._send_json(status())
            return
        if path == "/api/settings":
            self._send_json(get_env_settings())
            return
        if path == "/api/log":
            payload = tail_log().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        payload = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/start":
            self._send_json(start_overseer())
            return
        if path == "/api/stop":
            self._send_json(stop_overseer())
            return
        if path == "/api/settings":
            content_len = int(self.headers.get('Content-Length', 0))
            post_body = self.rfile.read(content_len)
            updates = json.loads(post_body.decode('utf-8'))
            update_env_settings(updates)
            self._send_json({"ok": True, "message": "Settings updated in .env."})
            return
        if path == "/api/flatten":
            # Logic to signal a flatten command
            # For now, we can write a command file or just log it
            (LOG_DIR / "flatten.cmd").touch()
            self._send_json({"ok": True, "message": "Flatten signal broadcast."})
            return
        self.send_error(404)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def server_is_running() -> bool:
    try:
        with urllib.request.urlopen(f"{APP_URL}/api/status", timeout=0.5) as response:
            return response.status == 200
    except Exception:
        return False


def run_server(open_browser: bool) -> None:
    if server_is_running():
        if open_browser:
            webbrowser.open(APP_URL)
        return

    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(APP_URL)).start()
    httpd.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="jogiapp KERNEL launcher")
    parser.add_argument("--open", action="store_true", help="open jogiapp in the browser")
    args = parser.parse_args()
    run_server(open_browser=args.open)


if __name__ == "__main__":
    main()
