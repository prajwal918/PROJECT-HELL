# INTEGRATION CHECKLIST
## NOVA & AEGIS → PROJECT HELL

---

## STATUS: INTEGRATION COMPLETE

**Location:** `C:\Users\jogip\OneDrive\Desktop\PROJECT HELL\nova\`

**Integration Points:**
- ✓ OVERSEER data directory linked
- ✓ OVERSEER bridge modules created
- ✓ Configuration updated for PROJECT HELL paths
- ✓ Documentation updated

---

## NEXT STEPS

### Priority 1: Update OVERSEER to Export L3 Data

OVERSEER needs to write L3 MBO data to a file that NOVA/AEGIS can read.

**Location:** `PROJECT HELL\overseer\main.py`

**Add to OVERSEER tick loop:**
```python
# Inside your tick processing function
async def export_l3_data(tick_data):
    l3_file = PROJECT_ROOT / "nova" / "overseer" / "data" / "l3_mbo.json"
    l3_data = {
        "timestamp": tick_data["timestamp"],
        "price": tick_data["price"],
        "bid": tick_data.get("bid", 0),
        "ask": tick_data.get("ask", 0),
        "volume": tick_data.get("volume", 0),
        "mbo": tick_data.get("mbo", {})
    }

    with open(l3_file, 'w') as f:
        json.dump(l3_data, f)
```

### Priority 2: Create Unified Project Launcher

Create a master launcher that starts everything in order.

**Location:** `PROJECT HELL\START_ALL.bat`

```batch
@echo off
echo Starting PROJECT HELL Trading Systems...
echo.

echo [1/4] Starting OVERSEER...
start "OVERSEER" cmd /k "cd /d C:\Users\jogip\OneDrive\Desktop\PROJECT HELL\overseer && python main.py"

timeout /t 5 /nobreak

echo [2/4] Starting NEXUS Rust Backend...
echo Note: NEXUS needs Rust compilation on Linux
echo For now, OVERSEER data will be used directly

timeout /t 2 /nobreak

echo [3/4] Starting NOVA (Phase 1)...
start "NOVA" cmd /k "cd /d C:\Users\jogip\OneDrive\Desktop\PROJECT HELL\nova\nova_logic && python main.py"

timeout /t 2 /nobreak

echo [4/4] Starting AEGIS (Phase 2)...
start "AEGIS" cmd /k "cd /d C:\Users\jogip\OneDrive\Desktop\PROJECT HELL\nova\aegis_logic && python main.py"

echo.
echo All systems starting...
echo Check individual windows for status
pause
```

### Priority 3: Test Integration

**Step 1: Verify OVERSEER is running**
```cmd
netstat -an | findstr 12347
```
Should show UDP listener on port 12347

**Step 2: Test NOVA integration**
```cmd
cd "C:\Users\jogip\OneDrive\Desktop\PROJECT HELL\nova\nova_logic"
python verify_setup.py
```

**Step 3: Test AEGIS integration**
```cmd
cd "C:\Users\jogip\OneDrive\Desktop\PROJECT HELL\nova\aegis_logic"
python verify_setup.py
```

**Step 4: Run test modes**
```cmd
# NOVA test mode
cd "C:\Users\jogip\OneDrive\Desktop\PROJECT HELL\nova\nova_logic"
python test_mode.py

# AEGIS test mode
cd "C:\Users\jogip\OneDrive\Desktop\PROJECT HELL\nova\aegis_logic"
python test_mode.py
```

### Priority 4: Configure Environment Variables

**NOVA .env:**
```bash
FRED_API_KEY=your_fred_api_key
NEXUS_WS_URL=ws://localhost:9001
USE_DEMO_MODE=true
```

**AEGIS .env:**
```bash
DERIV_API_TOKEN=your_deriv_token
NEXUS_WS_URL=ws://localhost:9001
USE_DEMO_MODE=true
```

---

## DEPENDENCY REQUIREMENTS

### What's Working Now
- ✓ OVERSEER (running, UDP feed active)
- ✓ Python 3.12.0
- ✓ All dependencies installed
- ✓ NOVA & AEGIS code complete
- ✓ Integration bridges created

### What Still Needs Setup
- [ ] OVERSEER L3 data export (code modification needed)
- [ ] NEXUS Rust backend (compile on Linux)
- [ ] FRED API key for NOVA
- [ ] Deriv API token for AEGIS

---

## IMMEDIATE ACTION ITEMS

1. **OVERSEER Modification (5 min)**
   - Add L3 data export to main.py
   - Write to `PROJECT HELL\nova\overseer\data\l3_mbo.json`

2. **Environment Setup (5 min)**
   - Get FRED API key
   - Get Deriv API token
   - Update .env files

3. **Test Integration (10 min)**
   - Run verify_setup.py for both systems
   - Run test_mode.py for both systems
   - Verify data flow

4. **Create Launcher (5 min)**
   - Create START_ALL.bat
   - Test startup sequence

---

## ALTERNATIVE: Direct OVERSEER Integration

Instead of using NEXUS WebSocket, you can make NOVA/AEGIS read directly from OVERSEER's internal structures.

**Modify NOVA's nexus_bridge.py to read from OVERSEER:**
```python
# Replace WebSocket connection with file reading
async def read_overseer_l3_data(self):
    l3_file = PROJECT_ROOT / "overseer" / "data" / "l3_mbo.json"
    while True:
        if l3_file.exists():
            with open(l3_file, 'r') as f:
                data = json.load(f)
                # Convert to Tick object
                tick = Tick(
                    timestamp_ns=data["timestamp"],
                    price=data["price"],
                    bid_size=data.get("bid", 0),
                    ask_size=data.get("ask", 0),
                    trade_size=data.get("volume", 0),
                    order_id=0,
                    action=3,
                    side=0,
                    flags=0,
                    seq_num=0,
                )
                await self.tick_queue.put(tick)
        await asyncio.sleep(0.1)
```

This eliminates the need for NEXUS backend entirely!

---

## RECOMMENDED NEXT STEP

**Option A: Fast Path (No Rust)**
Modify NOVA/AEGIS to read directly from OVERSEER's data files
- Time: 15 minutes
- Complexity: Low
- Benefit: Eliminates NEXUS dependency

**Option B: Full Integration (With NEXUS)**
Keep NEXUS WebSocket architecture
- Time: 1+ hours (Rust compilation)
- Complexity: High
- Benefit: Production-grade data pipeline

**Recommendation:** Start with Option A for quick testing, upgrade to Option B later.

---

**Which path would you like to take?**