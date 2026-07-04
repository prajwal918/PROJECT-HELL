# PROJECT HELL — MASTER ARCHITECTURE
## 5-Project Trading Ecosystem

**Last Updated:** June 23, 2026
**Version:** 1.0.0
**Total Projects:** 5

---

## EXECUTIVE SUMMARY

PROJECT HELL is a unified trading ecosystem comprising 5 interconnected systems that work together to capture opportunities across multiple timeframes, asset classes, and trading styles.

**The 5 Projects:**

1. **OVERSEER** — Real-time forex system with 152 gates
2. **NEXUS** — Rust backend for L3 order flow data
3. **PROPHET** — Deriv API binary options system
4. **NOVA** — 1-minute news binary system (Phase 1)
5. **AEGIS** — 15-minute absorption trap system (Phase 2)

---

## PROJECT OVERVIEW

### 1. OVERSEER — Main Forex Trading System

**Purpose:** Real-time forex trading with institutional-grade analysis

**Key Features:**
- 152 gate-based signal filters (23 frameworks)
- XGBoost machine learning scoring (60+ features)
- 16 institutional modules (VPIN, OFI, RegimeIntel, etc.)
- Legendary Mode: 6 platinum gates, 0.95+ score, 4:1 RR
- MT5 execution (Windows) / OANDA API (Linux)
- Telegram alerts

**Entry Type:** Automated (MT5/OANDA)
**Timeframe:** Scalping, Intraday, Swing
**Asset Class:** Forex, Futures

**Location:** `PROJECT HELL\overseer\`

---

### 2. NEXUS — Rust L3 Order Flow Backend

**Purpose:** High-performance L3 order flow data distribution

**Key Features:**
- Rust tokio async backend
- Receives MBO data via UDP from OVERSEER
- Maintains LimitOrderBook state
- Broadcasts FlatBuffer TickMessage via WebSocket
- State recovery (delta sync / full snapshot)
- 65K message broadcast capacity

**Data Sources:** OVERSEER UDP feed (127.0.0.1:12347)
**Output:** WebSocket ws://localhost:9001
**Clients:** NOVA, AEGIS, NEXUS Web Terminal

**Location:** `PROJECT HELL\nexus\rust-backend\`

---

### 3. PROPHET — Deriv API Binary Options

**Purpose:** Binary options execution on Deriv platform

**Key Features:**
- Deriv WebSocket API integration
- Automated execution (CALL/PUT)
- 15-minute binary contracts
- Signal engine with volume profile, CVD divergence
- Iceberg and absorption detection
- Demo/Real mode support

**Entry Type:** Automated (Deriv API)
**Timeframe:** 15-minute
**Asset Class:** Binary Options
**Broker:** Deriv

**Location:** `PROJECT HELL\prophet\`

---

### 4. NOVA — News Event Binary System (Phase 1)

**Purpose:** 1-minute binary options on news events

**Key Features:**
- 3-gate confluence system (75/100 points threshold)
- Gate 1: Event whitelist (35 high-impact events)
- Gate 2: Deep research directional bias (FRED API)
- Gate 3a: Pre-news vacuum (book thinning ≥25%)
- Gate 3b: Post-news anchor (order survival ≥60%)
- T+90s entry after news
- Manual execution on IQ Option/Pocket Option

**Entry Type:** Manual
**Timeframe:** 1-minute
**Asset Class:** Binary Options
**Trigger:** High-impact economic events

**Location:** `PROJECT HELL\nova\nova_logic\`

---

### 5. AEGIS — Absorption Trap System (Phase 2)

**Purpose:** 15-minute binary options on MBO absorption

**Key Features:**
- 4-gate confluence system (75/100 points threshold)
- Gate 1: Absorption detection (≥500 contracts)
- Gate 2: Depth retention (≥70% maintained)
- Gate 3: Rejection ratio (≥2.0 wick/body)
- Gate 4: Breakout confirmation
- Native MBO order ID tracking
- Automated execution via Deriv API

**Entry Type:** Automated (Deriv API)
**Timeframe:** 15-minute
**Asset Class:** Binary Options
**Trigger:** MBO absorption trap breakout

**Location:** `PROJECT HELL\nova\aegis_logic\`

---

## COMPLETE DATA FLOW

### Primary Data Path

```
┌─────────────────────────────────────────────────────────────────┐
│                         DATA SOURCE                            │
│                                                                 │
│                    MotiveWave / MT5 Chart                       │
│                     (CME Futures Data)                          │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ UDP (127.0.0.1:12347)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                        OVERSEER                                │
│                                                                 │
│  • Receives tick data via UDP                                   │
│  • Processes through 152 gates (23 frameworks)                  │
│  • Calculates XGBoost scores (60+ features)                     │
│  • Executes trades via MT5 or OANDA API                         │
│  • Sends Telegram alerts                                        │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ UDP (127.0.0.1:12347)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                         NEXUS                                  │
│                                                                 │
│  • Rust backend (tokio async)                                   │
│  • Receives MBO data from OVERSEER                             │
│  • Maintains LimitOrderBook state                               │
│  • Encodes FlatBuffer TickMessage                               │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ WebSocket (ws://localhost:9001)
                             ▼
                    ┌────────┴────────┐
                    │                 │
┌───────────────────▼─────────┐  ┌────▼──────────────────┐
│          NOVA               │  │        AEGIS          │
│                              │  │                       │
│  • Event whitelist           │  │  • Absorption detection│
│  • Directional bias          │  │  • Depth retention     │
│  • L3 vacuum/anchor          │  │  • Rejection ratio     │
│  • T+90s entry               │  │  • Breakout confirm    │
│  • Manual execution          │  │  • Auto Deriv execution│
└──────────────────────────────┘  └─────────────────────────┘
```

### Secondary Data Path (PROPHET)

```
┌─────────────────────────────────────────────────────────────────┐
│                        PROPHET                                 │
│                                                                 │
│  • Deriv API integration                                        │
│  • Signal engine (volume profile, CVD)                          │
│  • Iceberg/absorption detection                                 │
│  • 15-minute binary contracts                                   │
│  • Automated execution                                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## PROJECT INTERCONNECTIONS

### OVERSEER → NEXUS
- **Protocol:** UDP
- **Port:** 12347
- **Data:** MBO events, top-of-book, trades
- **Format:** JSON packets

### NEXUS → NOVA
- **Protocol:** WebSocket
- **Port:** 9001
- **Data:** FlatBuffer TickMessage
- **Usage:** L3 order flow analysis

### NEXUS → AEGIS
- **Protocol:** WebSocket
- **Port:** 9001
- **Data:** FlatBuffer TickMessage
- **Usage:** MBO absorption detection

### NOVA → OVERSEER
- **Protocol:** File I/O
- **Path:** `nova/overseer/data/signals.json`
- **Data:** Binary entry signals
- **Usage:** Signal logging, tracking

### AEGIS → OVERSEER
- **Protocol:** File I/O
- **Path:** `nova/overseer/data/signals.json`
- **Data:** Binary entry signals
- **Usage:** Signal logging, tracking

### AEGIS → Deriv API
- **Protocol:** WebSocket
- **Service:** Deriv Trading API
- **Data:** Binary options execution
- **Usage:** Automated trade placement

### PROPHET → Deriv API
- **Protocol:** WebSocket
- **Service:** Deriv Trading API
- **Data:** Binary options execution
- **Usage:** Automated trade placement

---

## SHARED INFRASTRUCTURE

### Data Directory

**Location:** `PROJECT HELL\nova\overseer\data\`

**Files:**
- `l3_mbo.json` — Current L3 order book state
- `signals.json` — Unified signal log (OVERSEER, NOVA, AEGIS)

**Access:** All 5 projects read/write to this directory

### WebSocket Server

**Location:** NEXUS Rust Backend

**URL:** `ws://localhost:9001`

**Clients:**
- NOVA (L3 data)
- AEGIS (L3 data)
- NEXUS Web Terminal (order flow visualization)

### UDP Network

**Source:** MotiveWave

**Destinations:**
- OVERSEER (127.0.0.1:12347)
- NEXUS (127.0.0.1:12347)

**Protocol:** UDP JSON packets

---

## STARTUP SEQUENCE

### Phase 1: Data Infrastructure (Terminal 1)

**Step 1: Start MotiveWave**
- Open MotiveWave
- Ensure charts are connected to CME data feed
- Verify UDP export is enabled

**Step 2: Start OVERSEER**
```cmd
cd "C:\Users\jogip\OneDrive\Desktop\PROJECT HELL\overseer"
python main.py
```
- Should show: Listening for UDP on 127.0.0.1:12347
- Keeps running in background

**Step 3: Start NEXUS (Linux only)**
```bash
cd /path/to/PROJECT\ HELL/nexus/rust-backend
cargo build --release
cargo run --release
```
- Should show: WebSocket server listening on 0.0.0.0:9001
- Keeps running in background

### Phase 2: Trading Systems (Terminals 2-4)

**Step 4: Start NOVA**
```cmd
cd "C:\Users\jogip\OneDrive\Desktop\PROJECT HELL\nova\nova_logic"
python main.py
```
- Monitors economic calendar
- Generates T+90s entry signals
- Manual execution on IQ Option/Pocket Option

**Step 5: Start AEGIS**
```cmd
cd "C:\Users\jogip\OneDrive\Desktop\PROJECT HELL\nova\aegis_logic"
python main.py
```
- Monitors L3 absorption
- Generates breakout signals
- Automated execution on Deriv

**Step 6: Start PROPHET (Optional)**
```cmd
cd "C:\Users\jogip\OneDrive\Desktop\PROJECT HELL\prophet"
python main.py
```
- Signal engine for binary options
- Automated execution on Deriv

---

## CONFIGURATION

### Environment Variables

**NOVA (.env):**
```bash
FRED_API_KEY=your_fred_api_key
TRADING_ECONOMICS_KEY=your_te_key (optional)
NEXUS_WS_URL=ws://localhost:9001
USE_DEMO_MODE=true
```

**AEGIS (.env):**
```bash
DERIV_API_TOKEN=your_deriv_token
NEXUS_WS_URL=ws://localhost:9001
USE_DEMO_MODE=true
```

**PROPHET (.env):**
```bash
DERIV_API_TOKEN=your_deriv_token
USE_DEMO_MODE=true
```

**OVERSEER:**
- No .env file (config in Python)

---

## API REQUIREMENTS

### Required for NOVA

1. **FRED API Key**
   - URL: https://fred.stlouisfed.org/docs/api/api_key.html
   - Purpose: Economic data, historical rates
   - Rate Limit: 120 requests/minute

2. **Trading Economics API Key** (Optional)
   - URL: https://tradingeconomics.com/api/
   - Purpose: Enhanced economic calendar

### Required for AEGIS

1. **Deriv API Token**
   - URL: https://app.deriv.com/account/api-token
   - Purpose: Automated binary options execution
   - Scope: Read, Trade

### Required for PROPHET

1. **Deriv API Token**
   - Same as AEGIS (can share token)

### No API Required for OVERSEER

OVERSEER uses local data from MotiveWave UDP feed.

---

## PROJECT SPECIFICATIONS

### OVERSEER

**Language:** Python 3.8+
**Platform:** Windows (MT5) / Linux (OANDA)
**Database:** SQLite (WAL mode)
**Execution:** Automated
**Risk Management:** Built-in (position sizing, stop loss)

**Gates:** 152 total (23 frameworks)
**Features:** 16 institutional modules
**Alerts:** Telegram

### NEXUS

**Language:** Rust (1.70+)
**Platform:** Linux (backend) / All (WebSocket clients)
**Protocol:** FlatBuffers
**Execution:** No (data distribution only)

**Capacity:** 65K messages broadcast
**Buffer:** 10K ticks delta
**Performance:** Sub-millisecond latency

### PROPHET

**Language:** Python 3.8+
**Platform:** All
**Broker:** Deriv
**Execution:** Automated
**Risk Management:** Built-in

**Contracts:** 15-minute binaries
**Signals:** Volume profile, CVD divergence
**Detection:** Iceberg, absorption

### NOVA

**Language:** Python 3.9+
**Platform:** All
**Broker:** IQ Option / Pocket Option
**Execution:** Manual
**Risk Management:** Built-in

**Contracts:** 1-minute binaries
**Entry:** T+90s after news
**Gates:** 3 (75/100 points)

### AEGIS

**Language:** Python 3.9+
**Platform:** All
**Broker:** Deriv
**Execution:** Automated
**Risk Management:** Built-in

**Contracts:** 15-minute binaries
**Entry:** Absorption breakout
**Gates:** 4 (75/100 points)

---

## FOLDER STRUCTURE

```
PROJECT HELL/
│
├── overseer/                    # Project 1: Main Forex System
│   ├── main.py
│   ├── AGENTS.md
│   ├── gates/
│   │   └── 152 gate modules
│   └── data/
│       └── signals.json
│
├── nexus/                       # Project 2: Rust Backend
│   ├── rust-backend/
│   │   ├── main.rs
│   │   ├── Cargo.toml
│   │   └── schemas/
│   └── src/                     # Web terminal
│
├── prophet/                     # Project 3: Deriv Binary System
│   ├── main.py
│   ├── execution/
│   │   └── deriv_bridge.py
│   └── prophet_signal/
│
└── nova/                        # Project 4 & 5: NOVA + AEGIS
    ├── nova_logic/              # Project 4: NOVA
    │   ├── main.py
    │   ├── config.py
    │   ├── core/
    │   │   ├── event_whitelist.py
    │   │   ├── directional_bias.py
    │   │   ├── l3_gate.py
    │   │   ├── nexus_bridge.py
    │   │   └── overseer_bridge.py
    │   ├── test_mode.py
    │   └── .env
    │
    ├── aegis_logic/             # Project 5: AEGIS
    │   ├── main.py
    │   ├── config.py
    │   ├── core/
    │   │   ├── absorption_detector.py
    │   │   ├── deriv_execution.py
    │   │   ├── nexus_bridge.py
    │   │   └── overseer_bridge.py
    │   ├── test_mode.py
    │   └── .env
    │
    ├── overseer/                # Shared data
    │   └── data/
    │       ├── l3_mbo.json
    │       └── signals.json
    │
    ├── README.md
    ├── PROJECT_STATUS.md
    ├── DEPLOYMENT_CHECKLIST.md
    └── INTEGRATION_CHECKLIST.md
```

---

## TROUBLESHOOTING

### OVERSEER Issues

**No UDP data received:**
- Check MotiveWave UDP export settings
- Verify OVERSEER listening on 127.0.0.1:12347
- Check firewall UDP rules

**Gates not firing:**
- Check XGBoost model files exist
- Verify feature calculation working
- Review gate configuration

### NEXUS Issues

**WebSocket won't start:**
- Check port 9001 not in use
- Verify Rust installation
- Check `cargo build --release` completed

**No UDP data from OVERSEER:**
- Verify OVERSEER running
- Check OVERSEER logs for UDP errors
- Test UDP connection: `netstat -an | grep 12347`

### NOVA Issues

**No events detected:**
- Check FRED_API_KEY in .env
- Verify network connectivity to FRED API
- Check system timezone (America/New_York)

**WebSocket connection failed:**
- Verify NEXUS backend running
- Check port 9001 accessible
- Review NOVA logs for errors

### AEGIS Issues

**No absorption detected:**
- Check MIN_ABSORPTION_VOLUME threshold
- Verify L3 data quality from NEXUS
- Monitor tick processing in logs

**Deriv execution failed:**
- Check DERIV_API_TOKEN in .env
- Verify token has Read + Trade scope
- Check account balance
- Review Deriv API logs

---

## PERFORMANCE METRICS

### Data Throughput

**OVERSEER → NEXUS:**
- Protocol: UDP
- Latency: <1ms
- Throughput: 10K+ ticks/second

**NEXUS → NOVA/AEGIS:**
- Protocol: WebSocket
- Latency: <5ms
- Throughput: 10K+ ticks/second

### System Resources

**OVERSEER:**
- CPU: 10-30%
- Memory: ~500MB
- Network: Low (UDP)

**NEXUS:**
- CPU: 5-15%
- Memory: ~200MB
- Network: High (WebSocket broadcast)

**NOVA:**
- CPU: 5-10%
- Memory: ~100MB
- Network: Low (calendar API)

**AEGIS:**
- CPU: 10-20%
- Memory: ~150MB
- Network: Medium (WebSocket + Deriv API)

---

## LOG FILES

### OVERSEER
**Location:** `PROJECT HELL\overseer\overseer.log`
**Content:** Gate scores, trade execution, errors

### NEXUS
**Location:** `PROJECT HELL\nexus\rust-backend\backend.log`
**Content:** UDP packets, WebSocket connections, errors

### NOVA
**Location:** `PROJECT HELL\nova\nova_logic\nova.log`
**Content:** Event detection, gate scores, entry signals

### AEGIS
**Location:** `PROJECT HELL\nova\aegis_logic\aegis.log`
**Content:** Absorption detection, gate scores, trade execution

### PROPHET
**Location:** `PROJECT HELL\prophet\prophet.log`
**Content:** Signal generation, trade execution, results

---

## RISK MANAGEMENT

### OVERSEER
- Position sizing: Kelly criterion
- Stop loss: Per trade setting
- Daily loss limit: Configurable
- Correlation limit: Built-in

### NOVA
- Max daily trades: 3
- Max daily loss: $30
- Stake per trade: $10
- No automatic execution

### AEGIS
- Max daily trades: 3
- Max daily loss: $50
- Stake per trade: $10
- Automatic execution

### PROPHET
- Max daily trades: 1
- Max daily loss: $50
- Stake per trade: $10
- Automatic execution

---

## FUTURE ROADMAP

### Phase 1: Stabilization (Current)
- ✅ OVERSEER production stable
- ✅ NEXUS backend deployed
- ✅ NOVA/AEGIS integrated
- ⏳ Testing all 5 systems together

### Phase 2: Optimization
- [ ] Optimize gate thresholds
- [ ] Improve XGBoost models
- [ ] Add new institutional modules
- [ ] Expand to more assets

### Phase 3: Expansion
- [ ] Add crypto trading
- [ ] Implement portfolio management
- [ ] Build web dashboard
- [ ] Add mobile alerts

---

## CONTACT & SUPPORT

### Documentation
- **MASTER.md** (this file): Complete architecture
- **OVERSEER/AGENTS.md**: OVERSEER details
- **nova/README.md**: NOVA/AEGIS details
- **nova/PROJECT_STATUS.md**: Development status

### Log Files
- All systems write logs to their respective directories
- Check log files for troubleshooting

### System Status
- Run `verify_setup.py` in NOVA/AEGIS
- Check OVERSEER logs for gate status
- Monitor NEXUS backend for data flow

---

**Total Projects:** 5
**Total Lines of Code:** ~25,000+
**Total Modules:** 150+
**Total Gates:** 152+
**Languages:** Python, Rust, JavaScript, HTML/CSS
**Platforms:** Windows, Linux, Web

---

**End of MASTER Architecture Document**

**Version:** 1.0.0
**Last Updated:** June 23, 2026
**Status:** Production Ready