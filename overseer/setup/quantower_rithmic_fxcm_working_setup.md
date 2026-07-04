# Quantower Rithmic + FXCM Working Setup

This note documents the working Quantower setup we built and tested.

## Current Goal

Use Quantower as the desktop data bridge for:

- Rithmic futures depth/order-flow data
- FXCM forex spot data
- OVERSEER Python backend via UDP/ZMQ

Quantower must stay open and connected while the strategy is running.

## Quantower Connections

Connect these in Quantower:

1. Rithmic
   - Used for CME futures depth/order-flow data.
   - Tested with futures contracts such as `6EM6`, `6BM6`, `6JM6`, `6AM6`, `6CM6`.

2. FXCM
   - Used for forex spot data.
   - Add forex symbols to the OVERSEER strategy input.
   - Confirm the FXCM connection is green before starting the strategy if spot forex pairs are included.

## Strategy To Run

Open Quantower:

```text
Strategies manager -> + -> OVERSEER v12 UDP Bridge
```

Only run one OVERSEER strategy instance at a time.

If old OVERSEER entries appear under Recent strategies, delete/ignore the old ones and run only the newest bridge.

## Current Installed Bridge Build

This is the build currently installed into Quantower:

```text
OVERSEER ALL PAIRS UDP Bridge 2026-06-01.5
```

Installed folder:

```text
C:\Quantower\TradingPlatform\v1.145.17\bin\Scripts\Strategies\OverseerAllPairsBridge
```

The installed build includes the full all-pairs default `Target symbols CSV` for:

- Rithmic CME FX futures
- FXCM forex spot pairs
- FXCM metals spot pairs

This build is UDP-only on purpose. NetMQ/ZMQ was removed because Quantower script loading failed to resolve the external NetMQ assembly. It still sends one startup UDP heartbeat as soon as the strategy starts, so `tools\udp_probe.py` can prove the strategy is actually loaded even before live market ticks arrive.

Another agent should not reinstall an older bridge over this one. If another agent needs to run the bridge, tell it to use `OVERSEER ALL PAIRS UDP Bridge 2026-06-01.5` and keep only one instance running.

## Target Symbols

Use this in `Target symbols CSV`:

```text
6EM6,6BM6,6JM6,6AM6,6CM6,6NM6,6SM6,6MM6,EUR/USD,GBP/USD,USD/JPY,AUD/USD,USD/CAD,NZD/USD,USD/CHF,EUR/GBP,EUR/JPY,GBP/JPY,AUD/JPY,CAD/JPY,CHF/JPY,NZD/JPY,EUR/AUD,EUR/CAD,EUR/CHF,EUR/NZD,GBP/AUD,GBP/CAD,GBP/CHF,GBP/NZD,AUD/CAD,AUD/CHF,AUD/NZD,CAD/CHF,NZD/CAD,NZD/CHF,XAU/USD,XAG/USD
```

If Quantower/FXCM uses no-slash symbols, use this alternate form:

```text
6EM6,6BM6,6JM6,6AM6,6CM6,6NM6,6SM6,6MM6,EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,NZDUSD,USDCHF,EURGBP,EURJPY,GBPJPY,AUDJPY,CADJPY,CHFJPY,NZDJPY,EURAUD,EURCAD,EURCHF,EURNZD,GBPAUD,GBPCAD,GBPCHF,GBPNZD,AUDCAD,AUDCHF,AUDNZD,CADCHF,NZDCAD,NZDCHF,XAUUSD,XAGUSD
```

The exact name must match the symbol name shown inside Quantower for that connection.

## Strategy Inputs

Recommended values:

```text
Target symbols CSV = 6EM6,6BM6,6JM6,6AM6,6CM6,6NM6,6SM6,6MM6,EUR/USD,GBP/USD,USD/JPY,AUD/USD,USD/CAD,NZD/USD,USD/CHF,EUR/GBP,EUR/JPY,GBP/JPY,AUD/JPY,CAD/JPY,CHF/JPY,NZD/JPY,EUR/AUD,EUR/CAD,EUR/CHF,EUR/NZD,GBP/AUD,GBP/CAD,GBP/CHF,GBP/NZD,AUD/CAD,AUD/CHF,AUD/NZD,CAD/CHF,NZD/CAD,NZD/CHF,XAU/USD,XAG/USD
UDP host           = 127.0.0.1
UDP port           = 65000
DOM depth          = 10
ZMQ port           = 5555
Enable ZMQ         = true
```

## Python Backend

Run the OVERSEER backend from the project root:

```powershell
python main.py
```

It listens for Quantower bridge packets and writes ticks/features to SQLite.

## What We Confirmed

Quantower successfully produced raw depth events into:

```text
logs/quantower_l3_raw.jsonl
```

Example fields observed:

```json
{
  "source": "quantower",
  "symbol": "6EM6",
  "quote": {
    "Price": 1.1672,
    "Size": 94,
    "Id": "ask_1.1672",
    "Priority": 0,
    "NumberOrders": 21,
    "Broker": null,
    "ImpliedSize": 1
  },
  "quotePriceType": "Ask"
}
```

## Important L3 Note

The Quantower strategy API exposed useful depth/order-flow fields:

- `Price`
- `Size`
- `Id`
- `NumberOrders`
- `ImpliedSize`
- `quotePriceType`

But the observed `Id` looked price-level based, such as:

```text
ask_1.1672
bid_1.1671
```

And `Priority` was `0` in the sampled data.

So this is confirmed useful DOM/MBP/order-count data, but it is not yet proven to be true exchange MBO with individual exchange order IDs.

## Files Involved

Main bridge:

```text
bridge/OverseerAllPairsBridge.cs
```

Quantower strategy install folder:

```text
C:\Quantower\TradingPlatform\v1.145.17\bin\Scripts\Strategies\OverseerAllPairsBridge
```

Important logs:

```text
logs/bridge.log
logs/quantower_l3_raw.jsonl
logs/backend.err.log
logs/backend.out.log
```

Database:

```text
database/overseer_trades.db
```

## Clean Restart Procedure

When changing the bridge DLL:

1. Stop all OVERSEER strategies in Quantower.
2. Close Quantower completely.
3. Build/copy the bridge DLL.
4. Reopen Quantower.
5. Connect Rithmic and FXCM.
6. Start only the newest OVERSEER bridge strategy.

## Do Not Run Two Bridges

Running two OVERSEER strategy instances caused duplicate UDP streams and stale old DLL behavior.

Always run only one:

```text
OVERSEER v12 UDP Bridge
```

## Forex Pair Addition

The bridge default symbol list now includes CME FX futures plus common FXCM forex pairs.

CME futures defaults:

```text
6EM6,6BM6,6JM6,6AM6,6CM6,6NM6,6SM6,6MM6
```

FXCM spot defaults:

```text
EUR/USD,GBP/USD,USD/JPY,AUD/USD,USD/CAD,NZD/USD,USD/CHF,EUR/GBP,EUR/JPY,GBP/JPY,AUD/JPY,CAD/JPY,CHF/JPY,NZD/JPY,EUR/AUD,EUR/CAD,EUR/CHF,EUR/NZD,GBP/AUD,GBP/CAD,GBP/CHF,GBP/NZD,AUD/CAD,AUD/CHF,AUD/NZD,CAD/CHF,NZD/CAD,NZD/CHF,XAU/USD,XAG/USD
```

If any pair is not found, open the Quantower symbol search for FXCM and copy the exact symbol name into `Target symbols CSV`.


## Raw L3 UDP mode

Current build `OVERSEER ALL PAIRS UDP Bridge 2026-06-01.5` sends every raw Quantower L2/L3 event to UDP immediately, before full DOM enrichment. This is intentional: `logs\quantower_l3_raw.jsonl` proved raw L3 data was flowing while the older full-payload UDP path could skip events when best bid/ask validation failed.

Agents must keep this bridge UDP-only. Do not re-add NetMQ/ZMQ inside the Quantower strategy; Quantower failed to load external NetMQ assemblies.

## Live Connection Test

To test whether Quantower is sending bridge data right now:

```powershell
python tools\udp_probe.py --host 0.0.0.0 --port 65000 --seconds 10
```

Expected result when the Quantower strategy is running:

```text
Packets received: 1 or more
```

If it shows:

```text
Packets received: 0
```

Then Quantower is connected visually, but the OVERSEER strategy is not currently sending packets. In that case:

1. Stop all old OVERSEER strategy instances.
2. Close and reopen Quantower.
3. Connect Rithmic and FXCM.
4. Add `OVERSEER ALL PAIRS UDP Bridge 2026-06-01.5`.
5. Confirm the strategy status is `Working`.
6. Run the UDP probe again.



