# Quantower → OVERSEER Bridge

This project already contains a **Quantower strategy** that streams Level 2 / Level 3 DOM data from Quantower directly into OVERSEER. This is the cleanest way to use your AMPConnect CQG credentials with OVERSEER.

## How it works

1. You install **Quantower** (AMP provides it free).
2. You connect Quantower to **AMP/CQG** using your demo credentials `demo120790` / `c__9fVQ5`.
3. You load the `OverseerBridge` strategy into Quantower.
4. The strategy reads Quantower's real-time DOM/tick events and forwards them to OVERSEER via:
   - **UDP** on `127.0.0.1:65000` (OVERSEER's default UDP listener), and/or
   - **ZMQ PUB** on `tcp://*:5555` topic `OVERSEER_L3`.

OVERSEER already listens on both of those, so no further changes are needed.

## Why this is better than scraping the CQG web app

- **Low latency:** Quantower receives native CQG market data, then the strategy pushes it locally.
- **Reliable:** no browser automation that breaks when CQG updates its website.
- **Officially supported:** AMP endorses Quantower + CQG.
- **Better data:** Quantower can provide true L2/L3 DOM via CQG.

## Requirements

- Windows 10/11 or Windows Server
- [.NET 8 SDK](https://dotnet.microsoft.com/download/dotnet/8.0)
- [Quantower](https://www.quantower.com/) installed
- AMPConnect CQG credentials

> **Note:** Quantower is a Windows desktop application. It cannot run in a Linux Docker container. For 24/7 headless operation, use a **Windows VPS** with RDP, install Quantower, and leave it logged in. Disconnecting RDP does not stop Quantower strategies.

## Step 1: Install and connect Quantower

1. Download Quantower from AMP:
   - https://www.ampfutures.com/bravo/downloads/quantower
   - or https://downloads.ampfutures.com/quantower
2. Install and launch Quantower.
3. Add connection: **Connections → AMP/CQG**.
4. Choose **Demo** server.
5. Enter username `demo120790` and password `c__9fVQ5`.
6. Connect and verify charts/DOM are updating.

Official AMP guide: https://faq.ampfutures.com/hc/en-us/articles/10801829315479-How-to-connect-CQG-to-Quantower

## Step 2: Build the OVERSEER bridge strategy

1. Find your Quantower installation. The csproj expects:
   ```
   C:\Quantower\TradingPlatform\v1.145.17\bin\TradingPlatform.BusinessLayer.dll
   ```
   If your version is different, set the path before building:
   ```powershell
   $env:QuantowerPath = "C:\Quantower\TradingPlatform\v1.xxxxx\bin"
   ```
2. Build the bridge DLL:
   ```powershell
   cd "C:\Users\jogip\OneDrive\Desktop\PROJECT HELL\overseer\bridge"
   dotnet build OverseerBridge.csproj -c Release
   ```
3. Copy the output to Quantower's strategies folder. Usually:
   ```
   %USERPROFILE%\Documents\Quantower\Strategies\OverseerBridge.dll
   ```
   Or use Quantower's **Strategy Manager → Import** feature.

## Step 3: Run the strategy in Quantower

1. In Quantower, open **Strategy Manager** or **Strategy Runner**.
2. Find `OVERSEER v12 UDP Bridge`.
3. Set parameters:
   - **Target symbols CSV:** e.g. `6E,6B,6J,ES,NQ,CL,GC` (use the CQG tickers Quantower shows)
   - **UDP host:** `127.0.0.1`
   - **UDP port:** `65000`
   - **DOM depth:** `10`
   - **ZMQ port:** `5555`
   - **Enable ZMQ:** `true`
   - **Log directory:** `C:\Users\jogip\OneDrive\Desktop\PROJECT HELL\overseer\logs`
4. Start the strategy.
5. Check the log file for "Subscribed to Level 2/Level 3 DOM" messages.

## Step 4: Start OVERSEER

```bash
cd "C:\Users\jogip\OneDrive\Desktop\PROJECT HELL\overseer"
.venv\Scripts\python main.py
```

OVERSEER will receive ticks from Quantower automatically.

## Files

```
overseer/bridge/
├── OverseerBridge.cs          # Main Quantower strategy (UDP + ZMQ)
├── OverseerBridge.csproj      # Build config
├── OverseerAllPairsBridge.cs  # Variant without ZMQ, UDP-only
└── OverseerAllPairsBridge.csproj
```

## Troubleshooting

### "Symbol not found"
Use the exact symbol name Quantower displays. CQG symbols differ from CME roots:
- E-mini S&P 500 → `EP`
- E-mini Nasdaq → `ENQ`
- Euro FX → `EU6`
- Crude Oil → `CLE`
- Gold → `GCE`

Full list: https://help.quantower.com/quantower/connections/connection-to-cqg-amp-futures

### "TradingPlatform.BusinessLayer.dll not found"
Update the `QuantowerPath` in `OverseerBridge.csproj` or set the environment variable before building:
```powershell
$env:QuantowerPath = "C:\Quantower\TradingPlatform\v1.xxxxx\bin"
dotnet build OverseerBridge.csproj -c Release
```

### No data in OVERSEER
- Confirm Quantower is connected and charts update.
- Confirm the bridge strategy is running.
- Confirm OVERSEER's UDP listener or ZMQ subscriber is active (check logs).
- If using ZMQ, make sure no other process is bound to port `5555`.

## Headless / VPS setup

For 24/7 operation:
1. Rent a Windows VPS (e.g. TradingFXVPS, Host4Fun, Azure, AWS).
2. RDP into the VPS.
3. Install Quantower and connect to AMP/CQG.
4. Build and load the bridge strategy.
5. Configure Windows Task Scheduler to auto-start Quantower on boot.
6. Set power options to never sleep.
7. Disconnect RDP — the strategy keeps running.

## Important

- This bridge uses your AMPConnect credentials inside Quantower, which is the intended use case.
- Demo accounts expire in 28 days.
- Do not use the CQG web-app scraper for live trading; use this Quantower bridge instead.
