# Quick Start Guide

## Prerequisites Checklist

- [ ] Python 3.9+ installed
- [ ] Rust installed (for NEXUS backend)
- [ ] OVERSEER running and feeding L3 data to NEXUS
- [ ] NEXUS Rust backend running on ws://localhost:9001
- [ ] FRED API key (for NOVA)
- [ ] Trading Economics API key (for NOVA, optional)
- [ ] Deriv API token (for AEGIS)

## Quick Start

### Option 1: Use Launcher
```cmd
cd C:\Users\jogip\nova
launch.bat
```

### Option 2: Manual Start

#### Start NOVA
```cmd
cd C:\Users\jogip\nova\nova_logic
copy .env.example .env
# Edit .env with your API keys
python main.py
```

#### Start AEGIS
```cmd
cd C:\Users\jogip\nova\aegis_logic
copy .env.example .env
# Edit .env with your Deriv API token
python main.py
```

## Troubleshooting

### NOVA Issues

**Error: Failed to connect to NEXUS**
- Ensure NEXUS Rust backend is running
- Check ws://localhost:9001 is accessible

**Error: FRED API failed**
- Verify FRED_API_KEY in .env is correct
- Get key at: https://fred.stlouisfed.org/docs/api/api_key.html

**No events detected**
- Check system timezone (should be America/New_York)
- Verify news calendars are accessible

### AEGIS Issues

**Error: Deriv connection failed**
- Verify DERIV_API_TOKEN in .env is correct
- Check token is valid (not expired)

**Error: No absorption detected**
- Ensure OVERSEER is feeding MBO data to NEXUS
- Check NEXUS WebSocket is receiving ticks

**Trade execution failed**
- Verify Deriv account has sufficient balance
- Check asset symbol (default: EUR/USD)

### Common Issues

**Port 9001 already in use**
- Another instance of NEXUS is running
- Kill existing process or change port in config

**ModuleNotFoundError**
- Install dependencies: `pip install -r requirements.txt`

**Permission denied on .env**
- Create .env manually from .env.example

## API Key Sources

| API | URL | Purpose |
|-----|-----|---------|
| FRED | https://fred.stlouisfed.org/docs/api/api_key.html | Event data, historical rates |
| Trading Economics | https://tradingeconomics.com/api/ | Economic calendar (optional) |
| Deriv | https://app.deriv.com/account/api-token | Binary options execution |

## Data Flow Verification

1. **OVERSEER → NEXUS**: UDP 127.0.0.1:12347
2. **NEXUS → NOVA/AEGIS**: WebSocket ws://localhost:9001

Verify with:
```cmd
netstat -an | findstr "12347"
netstat -an | findstr "9001"
```

## Log Files

- NOVA: `nova_logic/nova.log`
- AEGIS: `aegis_logic/aegis.log`

Check logs for detailed error messages.

## Performance

**NOVA:**
- CPU: Low (event-driven)
- Memory: ~50MB
- Network: Minimal (calendar API calls)

**AEGIS:**
- CPU: Medium (continuous tick processing)
- Memory: ~100MB
- Network: High (WebSocket stream)

## Support

For issues, check:
1. Log files
2. NEXUS backend logs: `PROJECT HELL\nexus\rust-backend\backend.log`
3. OVERSEER logs: `PROJECT HELL\overseer\overseer.log`