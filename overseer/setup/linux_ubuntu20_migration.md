# OVERSEER v12.9 Linux Migration Guide - Ubuntu 20.04 + Wine

Last updated: 2026-06-03  
Target host: Ubuntu 20.04 LTS  
Project path on Windows: `C:\Users\jogip\OneDrive\Desktop\MY_ORGANIZED_DESKTOP\dfg\urlr`

This guide explains how to move OVERSEER from Windows to Ubuntu while keeping the real order-flow data path working.

Important: Ubuntu 20.04 usually means **20.04 LTS**, not "20.0". Ubuntu 20.04 is old now. It can still work, but Python 3.12 is not the default system Python, so use `pyenv` or a separate Python install. Do not replace the system Python.

---

## 1. Current Working State Before Migration

The current confirmed working live path is:

```text
MotiveWave / Rithmic CME futures DOM
  -> UDP 127.0.0.1:65000
  -> core/hub_listener.py
  -> main.py
  -> DOM normalization + L3 scoring + gates + XGBoost + risk/drift checks
  -> SQLite + dashboard + optional MT5 execution
```

Current important facts:

- The Rithmic/MotiveWave feed is working.
- `DOM quality: crossed_book` was fixed by bid/ask normalization in `core/dom_quality.py`.
- Live ticks should show `bid <= ask` after normalization.
- Dashboard runs on `127.0.0.1:8080`.
- UDP listener runs on `0.0.0.0:65000`.
- Auto execution is currently off.
- Main remaining blocker is model drift safety:

```text
Trade blocked by risk limit: drift: Model drift detected
```

That is not a Linux problem. It is a protective trading rule. Keep it enabled for live money.

---

## 2. What Can Run On Linux

These parts can run natively on Ubuntu:

- `main.py`
- `core/hub_listener.py`
- SQLite database
- XGBoost inference/training
- gate registry / strategy logic
- dashboard
- Telegram alerts
- scrapers
- C lag engine compilation
- signal-only trading mode
- paper/shadow trading

These parts are Windows-sensitive:

- MetaTrader5 Python execution module
- MT5 terminal
- Quantower GUI
- R|Trader Pro GUI
- Some Rithmic/RAPI+ Windows SDK workflows
- MotiveWave if using Windows-only local setup

The clean Linux migration is:

```text
Rithmic/MotiveWave bridge somewhere
  -> UDP to Ubuntu server port 65000
  -> Ubuntu runs OVERSEER brain signal-only
  -> optional execution remains on Windows/MT5 node
```

---

## 3. Recommended Architecture

### Best Stable Setup

Use Ubuntu for the backend brain and keep Windows for GUI/data/execution pieces:

```text
Windows machine / VPS:
  MotiveWave + Rithmic + OVERSEER MotiveWave Bridge
  sends UDP packets to Ubuntu_IP:65000

Ubuntu 20.04 server:
  main.py receives UDP
  runs gates/model/risk/dashboard
  logs signals to SQLite
  sends Telegram alerts
  AUTO_EXECUTE=false

Optional Windows execution node:
  MT5 terminal + Python MetaTrader5
  receives approved signals from Ubuntu later
```

Why this is best:

- Rithmic GUI/data apps stay where they already work.
- Ubuntu handles the heavy Python analytics.
- MT5 stays on Windows where the official Python package works.
- You avoid Wine instability for live execution.

### Wine Setup

You said you already installed Wine. Wine can help run Windows GUI apps, but it does **not** make native Linux Python able to import the Windows-only `MetaTrader5` package.

Native Ubuntu Python:

```text
pip install MetaTrader5
```

will usually not install/use the MT5 Windows wheel because `requirements.txt` correctly has:

```text
MetaTrader5>=5.0.45; platform_system == "Windows"
```

So on Linux native mode:

```env
MT5_ENABLED=false
AUTO_EXECUTE=false
```

If you want MT5 through Wine, treat it as experimental:

```text
Wine MT5 terminal + Windows Python inside same Wine prefix
```

That means running a Windows Python interpreter under Wine, not normal Linux Python. It is possible to experiment, but it is not the recommended production path.

---

## 4. Ubuntu Base Setup

Run on Ubuntu:

```bash
sudo apt update
sudo apt upgrade -y

sudo apt install -y \
  git curl wget ca-certificates build-essential gcc g++ make \
  sqlite3 libsqlite3-dev pkg-config libffi-dev \
  python3-dev python3-venv python3-pip \
  unzip tmux htop ufw
```

For Python 3.12 on Ubuntu 20.04, use `pyenv` so you do not break system Python.

Install Python build dependencies:

```bash
sudo apt install -y \
  libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev \
  llvm libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev \
  libffi-dev liblzma-dev
```

Install `pyenv`:

```bash
curl https://pyenv.run | bash
```

Add this to `~/.bashrc`:

```bash
export PYENV_ROOT="$HOME/.pyenv"
command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
```

Reload shell:

```bash
source ~/.bashrc
```

Install Python 3.12:

```bash
pyenv install 3.12
pyenv global 3.12
python --version
```

Expected:

```text
Python 3.12.x
```

---

## 5. Copy Project To Ubuntu

Recommended Linux path:

```bash
mkdir -p ~/overseer
```

Copy the Windows project folder to:

```text
~/overseer/urlr
```

Examples:

### Option A - Git

```bash
cd ~/overseer
git clone <YOUR_REPO_URL> urlr
cd urlr
```

### Option B - SCP From Windows

From Windows PowerShell:

```powershell
scp -r "C:\Users\jogip\OneDrive\Desktop\MY_ORGANIZED_DESKTOP\dfg\urlr" user@UBUNTU_IP:~/overseer/
```

Then on Ubuntu:

```bash
cd ~/overseer/urlr
```

---

## 6. Create Python Virtual Environment

On Ubuntu:

```bash
cd ~/overseer/urlr
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

Important:

- `MetaTrader5` will be skipped on Linux because of the platform marker.
- `pywin32` will be skipped on Linux.
- This is correct for native Linux signal-only mode.

If `xgboost` install is slow, let it finish. If it fails, install build basics again:

```bash
sudo apt install -y build-essential cmake
pip install xgboost
```

---

## 7. Compile Lag Engine

Run:

```bash
cd ~/overseer/urlr
source .venv/bin/activate
python core/setup_lag.py
```

Expected result:

```text
lag_engine.so
```

If GCC is missing:

```bash
sudo apt install -y gcc build-essential
python core/setup_lag.py
```

---

## 8. Initialize Database

Run:

```bash
cd ~/overseer/urlr
source .venv/bin/activate
python database/setup_db.py
```

Expected:

```text
database/overseer_trades.db
```

SQLite WAL mode is used for safer concurrent dashboard + writer access.

---

## 9. Linux `.env` Settings

For first Linux launch, use signal-only mode:

```env
MT5_ENABLED=false
AUTO_EXECUTE=false
GATE_QUICK_REJECT=false
ZMQ_ENABLED=false

DASHBOARD_ENABLED=true
DASHBOARD_BIND=127.0.0.1
DASHBOARD_PORT=8080

UDP_DISCONNECT_TIMEOUT=30
OVERSEER_UDP_PORT=65000
```

If you want to open dashboard from another PC, change:

```env
DASHBOARD_BIND=0.0.0.0
DASHBOARD_API_KEY=choose_a_secret_token
```

Then firewall:

```bash
sudo ufw allow 8080/tcp
```

If you leave dashboard on localhost, use SSH tunnel instead:

```bash
ssh -L 8080:127.0.0.1:8080 user@UBUNTU_IP
```

Then open on your local browser:

```text
http://127.0.0.1:8080
```

---

## 10. UDP Feed Into Ubuntu

The backend listens on UDP port `65000`.

### If The Bridge Runs On The Same Ubuntu Machine

Bridge target:

```text
127.0.0.1:65000
```

No firewall needed.

### If MotiveWave/Rithmic Bridge Runs On Windows

Find Ubuntu IP:

```bash
ip addr
```

Example:

```text
192.168.1.55
```

Set the Windows bridge UDP target to:

```text
192.168.1.55:65000
```

Open Ubuntu firewall only for the Windows machine:

```bash
sudo ufw allow from WINDOWS_IP to any port 65000 proto udp
sudo ufw enable
```

Verify UDP arrives:

```bash
cd ~/overseer/urlr
source .venv/bin/activate
python tools/udp_probe.py --host 0.0.0.0 --port 65000 --seconds 10
```

Expected:

```text
packets > 0
```

If packets are zero:

1. Confirm Windows bridge is running.
2. Confirm bridge target is Ubuntu IP, not `127.0.0.1`.
3. Confirm Ubuntu firewall allows UDP 65000.
4. Confirm Windows firewall allows outbound UDP.
5. Confirm both machines are on same network/VPN.

---

## 11. Run OVERSEER On Ubuntu

Signal-only run:

```bash
cd ~/overseer/urlr
source .venv/bin/activate
python main.py
```

Expected logs:

```text
UDP listener bound and ready.
Dashboard: http://localhost:8080
OVERSEER v12 backend online
```

Verify dashboard:

```bash
curl -I http://127.0.0.1:8080
```

Verify DB ticks:

```bash
sqlite3 database/overseer_trades.db \
"select symbol,bid,ask,timestamp from tick_log order by rowid desc limit 10;"
```

Verify not crossed:

```bash
python - <<'PY'
import sqlite3
c = sqlite3.connect("database/overseer_trades.db")
rows = c.execute("select symbol,bid,ask,timestamp from tick_log order by rowid desc limit 20").fetchall()
for s,b,a,t in rows:
    print(s, b, a, "OK" if float(b) <= float(a) else "CROSSED", t)
PY
```

---

## 12. Run In `tmux`

Use this if you want it to continue after SSH disconnect:

```bash
tmux new -s overseer
cd ~/overseer/urlr
source .venv/bin/activate
python main.py
```

Detach:

```text
Ctrl+B, then D
```

Reattach:

```bash
tmux attach -t overseer
```

---

## 13. Optional `systemd` Service

Create service:

```bash
sudo nano /etc/systemd/system/overseer.service
```

Paste:

```ini
[Unit]
Description=OVERSEER v12.9 Backend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=YOUR_LINUX_USER
WorkingDirectory=/home/YOUR_LINUX_USER/overseer/urlr
Environment=PYTHONUNBUFFERED=1
ExecStart=/home/YOUR_LINUX_USER/overseer/urlr/.venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Replace `YOUR_LINUX_USER`.

Enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable overseer
sudo systemctl start overseer
```

Check:

```bash
sudo systemctl status overseer --no-pager
journalctl -u overseer -f
```

Stop:

```bash
sudo systemctl stop overseer
```

---

## 14. Wine Setup Notes

You said Wine is already installed. Verify:

```bash
wine --version
```

Create a separate Wine prefix for trading tools:

```bash
export WINEPREFIX="$HOME/.wine-overseer"
export WINEARCH=win64
winecfg
```

Install Windows helpers if you use `winetricks`:

```bash
sudo apt install -y winetricks
winetricks -q corefonts
```

### Running MT5 Under Wine

Install MT5 terminal:

```bash
export WINEPREFIX="$HOME/.wine-overseer"
wine mt5setup.exe
```

Run terminal:

```bash
export WINEPREFIX="$HOME/.wine-overseer"
wine "$WINEPREFIX/drive_c/Program Files/MetaTrader 5/terminal64.exe"
```

But remember:

```text
Linux Python + Wine MT5 is not the same as Windows Python + native MT5.
```

The official `MetaTrader5` Python package is Windows-oriented. If you need MT5 execution from Linux, use one of these:

### Recommended: Keep MT5 Execution On Windows

```text
Ubuntu OVERSEER signal engine
  -> Telegram / DB / future RPC signal
  -> Windows MT5 executor
```

This is safest.

### Experimental: Windows Python Inside Wine

This means:

1. Install Windows Python inside the Wine prefix.
2. Install `MetaTrader5` into that Windows Python.
3. Run a small executor script through Wine.
4. Keep MT5 terminal open in the same Wine prefix.

Example concept:

```bash
export WINEPREFIX="$HOME/.wine-overseer"
wine python.exe -m pip install MetaTrader5
wine python.exe wine_mt5_executor.py
```

This is not guaranteed. Test only on demo.

---

## 15. Headless Server Warning

If Ubuntu is a server with no desktop:

- Native OVERSEER backend is fine.
- Wine GUI apps like MT5, R|Trader Pro, Quantower, or MotiveWave need a GUI session.
- Use a real desktop session, RDP, VNC, or X server.
- Do not assume `systemd` can safely run GUI trading terminals.

For reliable 24/7:

```text
Ubuntu server: backend only
Windows VPS: MotiveWave/Rithmic/MT5 GUI apps
```

---

## 16. Linux Production Checklist

Before declaring Linux migration working:

```bash
cd ~/overseer/urlr
source .venv/bin/activate
```

Check Python:

```bash
python --version
```

Check imports:

```bash
python - <<'PY'
import numpy, pandas, xgboost, sklearn, imblearn, joblib, dotenv, aiohttp
print("imports ok")
PY
```

Check syntax:

```bash
python -m py_compile main.py core/hub_listener.py core/dom_quality.py core/dashboard.py tools/options_iv_scraper.py
```

Check lag engine:

```bash
python core/setup_lag.py
ls -l core/lag_engine.so
```

Check DB:

```bash
python database/setup_db.py
sqlite3 database/overseer_trades.db "pragma journal_mode;"
```

Check UDP:

```bash
python tools/udp_probe.py --host 0.0.0.0 --port 65000 --seconds 10
```

Run:

```bash
python main.py
```

Check dashboard:

```bash
curl http://127.0.0.1:8080 | head
```

Check logs:

```bash
grep -R "Traceback\|database is locked\|DOM quality: crossed_book" logs/ | tail -50
```

---

## 17. What To Tell Another Agent

Use this prompt:

```text
We are migrating OVERSEER v12.9 to Ubuntu 20.04. Read AGENTS.md and setup/linux_ubuntu20_migration.md first.

Do not enable live auto execution. Keep AUTO_EXECUTE=false.

The current backend feed should be MotiveWave/Rithmic UDP to port 65000. The Linux backend can run native in signal-only mode. MT5 execution is Windows-only unless an experimental Wine Windows-Python executor is built.

Verify:
1. Python 3.12 venv works.
2. requirements install without Windows-only packages.
3. core/setup_lag.py builds lag_engine.so.
4. database/setup_db.py initializes SQLite WAL DB.
5. UDP packets arrive on 0.0.0.0:65000.
6. main.py runs.
7. dashboard responds on 127.0.0.1:8080.
8. recent tick_log rows have bid <= ask.
9. no Traceback, no database is locked, no active DOM crossed_book blocker.
10. if trades/signals are blocked, confirm whether model drift safety is the only blocker.

If model drift is blocking, do not bypass it for live trading. Collect signal_log outcomes and retrain/calibrate thresholds.
```

---

## 18. Final Recommendation

For real institutional-level stability:

```text
Linux = analytics brain, database, dashboard, model, signal collection
Windows = Rithmic/MotiveWave/MT5 GUI execution components
```

Use Wine only for experiments or when you can supervise it. For live money, keep MT5 on Windows until a separate tested execution node exists.

