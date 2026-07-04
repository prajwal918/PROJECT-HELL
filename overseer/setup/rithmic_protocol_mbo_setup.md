# Rithmic Protocol MBO Setup

This is the no-Quantower path for OVERSEER.

## What This Uses

- Rithmic Protocol Buffer websocket gateway
- `async-rithmic` Python package
- Rithmic username/password/system credentials
- Market By Order / depth-by-order entitlement

This does not scrape Quantower. It also does not rely on Quantower being open.

R|Trader Pro may still be useful to confirm the account is active and market data is live, but this connector logs in directly to the Rithmic Protocol gateway.

## Required Environment Variables

Set these in PowerShell before starting the bridge:

```powershell
$env:RITHMIC_USER="YOUR_RITHMIC_USERNAME"
$env:RITHMIC_PASSWORD="YOUR_RITHMIC_PASSWORD"
$env:RITHMIC_SYSTEM_NAME="Rithmic Paper Trading"
$env:RITHMIC_URL="wss://rituz00100.rithmic.com:443"
$env:RITHMIC_SYMBOLS="6EM6:CME,6BM6:CME,6JM6:CME,6AM6:CME,6CM6:CME,6NM6:CME"
```

If your broker uses a different Rithmic system name, set that exact value instead.

## Start The Direct MBO Bridge

```powershell
python tools\rithmic_mbo_udp_bridge.py
```

The bridge sends OVERSEER-compatible UDP packets to:

```text
127.0.0.1:65000
```

It also writes raw depth-by-order protobuf-decoded events here:

```text
logs/rithmic_mbo_events.jsonl
```

## How To Confirm True MBO

Open:

```text
logs/rithmic_mbo_events.jsonl
```

True MBO / depth-by-order should contain fields such as:

- `exchange_order_id`
- `depth_order_priority`
- `depth_price`
- `depth_size`
- `transaction_type`
- `update_type`

If Rithmic rejects the depth-by-order subscription or these fields are empty, the account likely has order book data but not true MBO entitlement.

## Important Clarification

The pasted `RithmicTickerApi` / `RithmicEnvironment` sample is not the API exposed by the installed `async-rithmic` package. The working package exposes `RithmicClient`.

The connector in `tools/rithmic_mbo_udp_bridge.py` uses the actual installed package API.
