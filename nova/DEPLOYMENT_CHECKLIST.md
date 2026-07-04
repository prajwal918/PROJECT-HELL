# DEPLOYMENT CHECKLIST
## NOVA & AEGIS Trading Systems

---

## PRE-DEPLOYMENT CHECKLIST

### 1. API Keys Required

- [ ] **FRED API Key** (for NOVA)
  - URL: https://fred.stlouisfed.org/docs/api/api_key.html
  - Purpose: Economic data, historical rates
  - Add to: `nova_logic\.env` as `FRED_API_KEY=your_key_here`

- [ ] **Trading Economics API Key** (for NOVA - optional)
  - URL: https://tradingeconomics.com/api/
  - Purpose: Enhanced economic calendar
  - Add to: `nova_logic\.env` as `TRADING_ECONOMICS_KEY=your_key_here`

- [ ] **Deriv API Token** (for AEGIS)
  - URL: https://app.deriv.com/account/api-token
  - Purpose: Automated binary options execution
  - Scope: Read, Trade
  - Add to: `aegis_logic\.env` as `DERIV_API_TOKEN=your_token_here`

### 2. System Prerequisites

- [ ] **Python 3.9+** installed (confirmed: 3.12.0 ✓)
- [ ] **Rust toolchain** installed (for NEXUS backend)
  - Install: `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`
  - Verify: `rustc --version`

- [ ] **OVERSEER running**
  - Check: `python verify_setup.py` should show OVERSEER as PASS
  - Start if needed: `cd "C:\Users\jogip\OneDrive\Desktop\PROJECT HELL\overseer" && python main.py`

### 3. File Configuration

- [ ] **NOVA .env file configured**
  ```bash
  cd C:\Users\jogip\nova\nova_logic
  copy .env.example .env
  # Edit .env with your API keys
  ```

- [ ] **AEGIS .env file configured**
  ```bash
  cd C:\Users\jogip\nova\aegis_logic
  copy .env.example .env
  # Edit .env with your Deriv API token
  ```

### 4. Build NEXUS Rust Backend

**ON LINUX:**
```bash
cd /path/to/PROJECT\ HELL/nexus/rust-backend
cargo build --release
cargo run --release
```

**Expected Output:**
```
[NEXUS] Backend starting...
[NEXUS] Listening for OVERSEER UDP on 127.0.0.1:12347
[NEXUS] WebSocket server listening on 0.0.0.0:9001
```

### 5. Verify All Systems

```bash
cd C:\Users\jogip\nova\nova_logic
python verify_setup.py

cd C:\Users\jogip\nova\aegis_logic
python verify_setup.py
```

**Expected:** All 6 checks should PASS for both systems

---

## DEPLOYMENT SEQUENCE

### Phase 1: Infrastructure Start

1. **Start OVERSEER** (if not already running)
   ```cmd
   cd "C:\Users\jogip\OneDrive\Desktop\PROJECT HELL\overseer"
   python main.py
   ```
   - Keep this terminal open

2. **Start NEXUS Rust Backend** (on Linux)
   ```bash
   cd /path/to/PROJECT\ HELL/nexus/rust-backend
   cargo run --release
   ```
   - Keep this terminal open
   - Should show WebSocket server listening on port 9001

3. **Verify Data Flow**
   - Check OVERSEER logs: Should show UDP packets to NEXUS
   - Check NEXUS logs: Should show receiving MBO events
   - Verify WebSocket is accessible: `netstat -an | grep 9001`

### Phase 2: Launch NOVA

1. **Open new terminal**

2. **Navigate to NOVA directory**
   ```cmd
   cd C:\Users\jogip\nova\nova_logic
   ```

3. **Run verification**
   ```cmd
   python verify_setup.py
   ```

4. **Start NOVA**
   ```cmd
   python main.py
   ```
   - OR use launcher: `start_nova.bat`

5. **Monitor startup logs**
   ```
   === NOVA Signal Engine Starting ===
   Target Asset: EUR/USD
   Trade Duration: 60s
   Entry Delay: T+90s
   Mode: DEMO
   [NEXUS] Connected to localhost:9001
   Starting tick processing loop...
   ```

6. **Watch for signals**
   - NOVA will continuously monitor economic calendar
   - Signals will appear in console and nova.log
   - Entry triggers show: `🚀 ENTRY TRIGGERED 🚀`

### Phase 3: Launch AEGIS

1. **Open new terminal**

2. **Navigate to AEGIS directory**
   ```cmd
   cd C:\Users\jogip\nova\aegis_logic
   ```

3. **Run verification**
   ```cmd
   python verify_setup.py
   ```

4. **Start AEGIS**
   ```cmd
   python main.py
   ```
   - OR use launcher: `start_aegis.bat`

5. **Monitor startup logs**
   ```
   === AEGIS Signal Engine Starting ===
   Target Asset: EUR/USD
   Trade Duration: 900s (15 min)
   Stake: $10.00
   Absorption Threshold: 500.0 contracts
   [AEGIS] Connected to Deriv - DEMO mode
   [NEXUS] Connected to localhost:9001
   Starting tick processing loop...
   ```

6. **Watch for signals**
   - AEGIS will continuously monitor for absorption
   - Signals show: `🔍 ABSORPTION DETECTED 🔍`
   - Trades execute automatically: `💹 EXECUTING TRADE 💹`

---

## MONITORING CHECKLIST

### Daily Monitoring

- [ ] Check log files for errors
  - `nova_logic/nova.log`
  - `aegis_logic/aegis.log`
  - `nexus/rust-backend/backend.log`

- [ ] Verify WebSocket connections
  - Check NOVA logs: `[NEXUS] Connected`
  - Check AEGIS logs: `[NEXUS] Connected`

- [ ] Monitor API usage
  - FRED API: Check rate limits (120 requests/minute)
  - Deriv API: Check API token usage

- [ ] Review trade results
  - NOVA: Manual trades (track manually)
  - AEGIS: Check logs for `📊 TRADE RESULT 📊`

### Weekly Monitoring

- [ ] Analyze signal performance
  - Count total signals generated
  - Calculate win rate
  - Review failed gate scores

- [ ] Review risk metrics
  - Daily loss limits respected
  - Trade count limits respected
  - Stake amounts within limits

- [ ] Optimize thresholds (if needed)
  - Adjust `BOOK_THINNING_THRESHOLD`
  - Adjust `ANCHOR_RATIO_THRESHOLD`
  - Adjust `MIN_ABSORPTION_VOLUME`

---

## TROUBLESHOOTING GUIDE

### NOVA Issues

**No events detected**
- Check: Calendar API keys in .env
- Check: Network connectivity to API endpoints
- Check: System timezone (should be America/New_York)
- Log: `nova.log` for API errors

**WebSocket connection failed**
- Check: NEXUS backend running on port 9001
- Check: Firewall blocking port 9001
- Check: NEXUS backend logs for errors
- Log: `nova.log` for connection errors

**Gate scores always 0**
- Check: L3 data flowing from OVERSEER → NEXUS
- Check: NEXUS receiving UDP packets (127.0.0.1:12347)
- Check: Book state updating in NEXUS logs
- Log: `nova.log` for tick processing

### AEGIS Issues

**No absorption detected**
- Check: MIN_ABSORPTION_VOLUME threshold
- Check: L3 data quality from NEXUS
- Check: Absorption detector logs
- Log: `aegis.log` for tick processing

**Deriv trade execution failed**
- Check: DERIV_API_TOKEN in .env
- Check: Token has Read + Trade scope
- Check: Account has sufficient balance
- Check: Asset symbol (default: EUR/USD)
- Log: `aegis.log` for API errors

**Trade results not received**
- Check: Deriv WebSocket connection
- Check: `listen_results()` task running
- Check: Contract ID in pending trades
- Log: `aegis.log` for result tracking

### NEXUS Issues

**WebSocket server won't start**
- Check: Port 9001 not already in use
- Check: `cargo build --release` completed successfully
- Check: Rust version (1.70+ recommended)
- Log: `backend.log` for startup errors

**No UDP data received**
- Check: OVERSEER running
- Check: OVERSEER sending to correct UDP port (12347)
- Check: Network firewall allowing UDP
- Log: `backend.log` for UDP packets

**High memory usage**
- Check: Delta buffer size (10,000 ticks)
- Check: Broadcast channel capacity (65,536)
- Reduce: `DELTA_BUFFER_CAPACITY` in main.rs
- Reduce: `BROADCAST_CAPACITY` in main.rs

---

## ROLLBACK PROCEDURES

### Emergency Stop

**Stop NOVA:**
```cmd
# In NOVA terminal: Ctrl+C
# Or: taskkill /F /IM python.exe (be careful - kills all Python)
```

**Stop AEGIS:**
```cmd
# In AEGIS terminal: Ctrl+C
# Or: taskkill /F /IM python.exe (be careful)
```

**Stop NEXUS:**
```bash
# In NEXUS terminal: Ctrl+C
# Or: pkill -f nexus-flow-backend
```

### Failed Deployment

If NEXUS backend fails to start:
1. Keep OVERSEER running (data source)
2. Defer NOVA/AEGIS deployment until NEXUS fixed
3. Check Rust installation and compilation errors

If API keys fail:
1. Verify keys are correct
2. Check API key status (not revoked)
3. Generate new keys if needed
4. Update .env files

If WebSocket fails:
1. Check NEXUS backend status
2. Verify port 9001 is accessible
3. Check firewall rules
4. Restart NEXUS backend

---

## SUCCESS CRITERIA

### NOVA Deployment Success

- [ ] All 6 setup checks pass
- [ ] NOVA connects to NEXUS WebSocket
- [ ] Calendar events are fetched successfully
- [ ] Event whitelist filters correctly
- [ ] Deep research analysis completes
- [ ] L3 book tracking works
- [ ] Gate scores calculate correctly
- [ ] Entry signals generate at T+90s
- [ ] Log file writes successfully

### AEGIS Deployment Success

- [ ] All 6 setup checks pass
- [ ] AEGIS connects to NEXUS WebSocket
- [ ] AEGIS connects to Deriv API
- [ ] Absorption detection works
- [ ] Gate scores calculate correctly
- [ ] Breakout confirmation triggers
- [ ] Trades execute via Deriv API
- [ ] Trade results received
- [ ] Log file writes successfully

### Overall System Success

- [ ] Data flow: OVERSEER → NEXUS → NOVA/AEGIS
- [ ] No errors in any log files
- [ ] Both systems running simultaneously
- [ ] WebSocket connections stable
- [ ] API rate limits respected
- [ ] Risk management limits enforced

---

## POST-DEPLOYMENT TASKS

### First 24 Hours

- [ ] Monitor all systems for errors
- [ ] Check log files every 4 hours
- [ ] Verify signal generation (even if not executing)
- [ ] Test emergency stop procedures
- [ ] Document any issues found

### First Week

- [ ] Collect signal performance data
- [ ] Analyze win rate and confluence patterns
- [ ] Review failed trades
- [ ] Optimize thresholds if needed
- [ ] Update documentation with findings

### First Month

- [ ] Conduct full system performance review
- [ ] Update risk parameters based on results
- [ ] Consider adding additional gates
- [ ] Evaluate expansion to other assets
- [ ] Document lessons learned

---

## CONTACT & SUPPORT

### Documentation
- README.md: System overview
- QUICK_START.md: Quick start guide
- PROJECT_STATUS.md: Current status

### Log Files
- nova.log: NOVA logs
- aegis.log: AEGIS logs
- backend.log: NEXUS logs
- overseer.log: OVERSEER logs

### API Support
- FRED: https://fred.stlouisfed.org/docs/api/
- Trading Economics: https://tradingeconomics.com/api/
- Deriv: https://developers.deriv.com/

---

**Last Updated:** June 23, 2026
**Version:** 1.0.0
**Status:** READY FOR DEPLOYMENT