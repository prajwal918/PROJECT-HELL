# CQG AMPConnect Integration for OVERSEER

## Recommended path: use the existing Quantower bridge

The project already has a working **Quantower → OVERSEER bridge**. This is the best way to use your AMPConnect CQG credentials:

👉 **See `overseer/QUANTOWER_BRIDGE.md` for full instructions.**

Why Quantower is better than the CQG WebAPI or web scraping:
- Uses your AMPConnect credentials the way AMP intended.
- Native CQG market data inside Quantower.
- Low-latency local push to OVERSEER.
- No browser fragility, no API entitlement blockers.

## Alternative: CQG WebAPI bridge

If you prefer a direct API connection (no Quantower GUI), I also built `overseer/tools/cqg_mbo_bridge.py`.

### What was done

1. **CQG WebAPI Python bindings added** to `overseer/core/cqg_webapi/`.
2. **Credentials stored securely** in `overseer/.env`.
3. **Bridge script created**: `overseer/tools/cqg_mbo_bridge.py`
4. **Wired into `overseer/main.py`** — auto-starts as subprocess when `CQG_ENABLED=true`.
5. **Launcher**: `overseer/tools/start_cqg_bridge.bat`.

### Current blocker

When the bridge connects with your AMPConnect demo credentials, CQG returns:

```
CQG logon failed: Trader is not enabled to use CQG Web API Test. Contact your FCM. (code=101)
```

Your account exists, but **AMP/EdgeClear has not enabled CQG WebAPI entitlement**. Call them and ask to enable **CQG Web API Test (demo)** for username `demo120790`.

### Important notes

- CQG WebAPI officially provides Level 1 + Level 2 data; level 7 adds detailed DOM but is not true L3 MBO.
- Demo accounts expire in 28 days.

## Files changed / added

```
overseer/
├── .env                              (appended CQG_* variables)
├── overseer_forex/.env.example       (added CQG template)
├── core/cqg_webapi/                  (CQG WebAPI protobuf bindings)
├── tools/cqg_mbo_bridge.py           (CQG WebAPI bridge)
├── tools/start_cqg_bridge.bat        (Windows launcher)
├── bridge/OverseerBridge.cs          (Quantower strategy)
├── bridge/build-quantower-bridge.ps1 (Quantower build script)
├── QUANTOWER_BRIDGE.md               (Quantower setup guide)
└── CQG_INTEGRATION.md                (this file)
```
