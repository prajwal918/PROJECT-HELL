# NOVA & AEGIS — Integrated into PROJECT HELL

**Location:** `C:\Users\jogip\OneDrive\Desktop\PROJECT HELL\nova\`

**Integration with OVERSEER:**
- Shared data directory: `PROJECT HELL\nova\overseer\data\`
- L3 MBO data sharing via JSON files
- Signal logging to unified OVERSEER signals file
- Framework score integration

---

## Project Structure

```
PROJECT HELL/
├── overseer/                    # Main forex system (152 gates)
│   ├── main.py
│   ├── AGENTS.md
│   └── data/
│       ├── l3_mbo.json          # Shared L3 data
│       └── signals.json         # Unified signal log
│
├── nova/                        # Binary options systems
│   ├── nova_logic/              # Phase 1: NOVA (1-min news)
│   │   ├── main.py
│   │   ├── config.py            # Links to overseer/data
│   │   ├── core/
│   │   │   ├── overseer_bridge.py  # OVERSEER integration
│   │   │   ├── nexus_bridge.py     # NEXUS WebSocket
│   │   │   ├── event_whitelist.py
│   │   │   ├── directional_bias.py
│   │   │   └── l3_gate.py
│   │   └── test_mode.py
│   │
│   └── aegis_logic/             # Phase 2: AEGIS (15-min absorption)
│       ├── main.py
│       ├── config.py            # Links to overseer/data
│       ├── core/
│       │   ├── overseer_bridge.py  # OVERSEER integration
│       │   ├── nexus_bridge.py     # NEXUS WebSocket
│       │   ├── absorption_detector.py
│       │   └── deriv_execution.py
│       └── test_mode.py
│
├── nexus/                       # Rust backend (shared L3 data)
│   └── rust-backend/
│       ├── main.rs
│       └── Cargo.toml
│
└── vanguard/                     # Deriv trading (existing)
```

---

## Integration Points

### 1. Data Sharing

**OVERSEER → NOVA/AEGIS:**
```
OVERSEER (UDP 12347)
    ↓
NEXUS (WebSocket 9001)
    ↓
NOVA / AEGIS (nexus_bridge.py)
```

**NOVA/AEGIS → OVERSEER:**
```
NOVA / AEGIS (overseer_bridge.py)
    ↓
PROJECT HELL\nova\overseer\data\signals.json
    ↓
OVERSEER (signal logging)
```

### 2. Configuration

Both systems now reference:
```python
OVERSEER_DIR = PROJECT_ROOT / "overseer"
OVERSEER_DATA_DIR = OVERSEER_DIR / "data"
OVERSEER_L3_DATA_PATH = OVERSEER_DATA_DIR / "l3_mbo.json"
OVERSEER_SIGNALS_PATH = OVERSEER_DATA_DIR / "signals.json"
```

### 3. Signal Integration

NOVA and AEGIS write signals to OVERSEER's unified signal log:
```json
{
  "timestamp": "2026-06-23T12:00:00",
  "source": "NOVA" or "AEGIS",
  "direction": "UP" or "DOWN",
  "confluence": 85,
  "asset": "EUR/USD"
}
```

---

## Unified Startup

### Start All Systems

**Terminal 1 - OVERSEER:**
```cmd
cd "C:\Users\jogip\OneDrive\Desktop\PROJECT HELL\overseer"
python main.py
```

**Terminal 2 - NEXUS:**
```bash
cd /path/to/PROJECT HELL/nexus/rust-backend
cargo run --release
```

**Terminal 3 - NOVA:**
```cmd
cd "C:\Users\jogip\OneDrive\Desktop\PROJECT HELL\nova\nova_logic"
python main.py
```

**Terminal 4 - AEGIS:**
```cmd
cd "C:\Users\jogip\OneDrive\Desktop\PROJECT HELL\nova\aegis_logic"
python main.py
```

---

## Benefits of Integration

1. **Unified Data Pipeline:** All systems share the same L3 data source
2. **Centralized Logging:** All signals logged to one file
3. **Simplified Deployment:** One project directory for all trading systems
4. **Framework Score Access:** NOVA/AEGIS can read OVERSEER's framework scores
5. **Shared Configuration:** Centralized environment variables

---

## Updated File Locations

| File | Old Location | New Location |
|------|--------------|--------------|
| NOVA config.py | `nova/nova_logic/config.py` | `nova/nova_logic/config.py` |
| AEGIS config.py | `nova/aegis_logic/config.py` | `nova/aegis_logic/config.py` |
| NOVA main.py | `nova/nova_logic/main.py` | `nova/nova_logic/main.py` |
| AEGIS main.py | `nova/aegis_logic/main.py` | `nova/aegis_logic/main.py` |
| OVERSEER integration | None | `nova/nova_logic/core/overseer_bridge.py` |

---

## Next Steps

1. [ ] Update OVERSEER to write L3 data to `nova/overseer/data/l3_mbo.json`
2. [ ] Update OVERSEER to read signals from NOVA/AEGIS
3. [ ] Test data flow: OVERSEER → NEXUS → NOVA/AEGIS → OVERSEER
4. [ ] Update OVERSEER AGENTS.md to document integration
5. [ ] Create unified launcher script for all systems

---

**Last Updated:** June 23, 2026
**Version:** 2.0.0 (Integrated with OVERSEER)