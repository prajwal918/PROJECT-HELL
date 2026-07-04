# OpenCode Context Handoff

Project: OVERSEER v12.9  
Workspace: `C:\Users\jogip\OneDrive\Desktop\MY_ORGANIZED_DESKTOP\dfg\urlr`  
OpenCode session command:

```powershell
opencode -s ses_185f02f88ffeJ1khb32BywSNfm
```

## Short Answer

The live data pipeline is working now.

Current working path:

```text
MotiveWave / Rithmic CME futures DOM
  -> UDP 127.0.0.1:65000
  -> core/hub_listener.py
  -> main.py
  -> DOM normalization + L3 scoring + gates + model + risk/drift checks
  -> SQLite + dashboard + optional MT5 execution
```

Important: trade execution is still blocked by model drift safety. That is expected and protective, not a connection failure.

Current blocker:

```text
Trade blocked by risk limit: drift: Model drift detected
```

Do not bypass this for live trading. Use signal-only mode until enough fresh live outcomes are collected and the model is retrained/calibrated.

## Source Of Truth

Read this first:

```text
AGENTS.md
```

The latest added section is:

```text
v12.9.2 Live Handoff (2026-06-03) - MotiveWave/Rithmic DOM Normalization + Runtime Stability
```

That section contains the current state, fixes, verification commands, and next work.

## Conversation Summary

The user originally wanted a full OVERSEER v12 institutional forex HFT-style system with:

- C# / Quantower bridge
- Python UDP listener
- C lag engine
- SQLite risk triggers
- 94+ gate registry
- XGBoost training
- MT5 execution
- Docker/backend infra
- R|Trader Pro / Rithmic setup guide

During live setup, the user tried:

- R|Trader Pro with Allow Plug-ins
- R|Trader Pro quote board / Excel streaming
- Quantower Rithmic connection
- Strategy Manager
- Rithmic Level 3 / DOM / MBO style data
- FXCM connection inside Quantower
- MotiveWave/Rithmic live feed

The final chosen real-time feed path is MotiveWave/Rithmic over UDP, not FXCM and not Quantower as the backend feed.

Quantower can be open visually and FXCM can connect visually, but backend trading decisions currently use the CME futures/Rithmic UDP feed because that is where the order-flow / DOM / L3-style data exists.

## What Was Fixed

### 1. DOM crossed-book false block

Problem:

MotiveWave/Rithmic sometimes sent CME FX futures with inverted bid/ask:

```text
bid > ask
```

That caused:

```text
DOM quality: crossed_book
```

and blocked trades/signals.

Fix:

`core/dom_quality.py` now auto-normalizes crossed books by swapping:

```text
bid <-> ask
bid_size <-> ask_size
```

It also marks:

```python
tick["dom_auto_swapped"] = True
```

Result:

Recent `tick_log` rows should show `bid <= ask`.

### 2. Tick buffering / DB commit issue

Problem:

`main.py` had tick buffering inside the slow 500-tick maintenance branch, so normal tick persistence/commit timing was wrong.

Fix:

`_tick_buffer.append(...)` now runs for every valid tick. Batch commits still use `COMMIT_INTERVAL_TICKS`.

### 3. SQLite lock stability

Problem:

Dashboard/runtime readers could fight with the live write loop and cause lock warnings.

Fixes:

- Runtime SQLite connection uses WAL/autocommit/busy timeout.
- Dashboard uses safer read connection, timeout, cache, and `ThreadingHTTPServer`.
- Extra commits were added after signal/trade logging.

Latest scan after fixes showed no new `database is locked` errors.

### 4. Runtime crashes fixed

Fixed crash chain:

- DB connection closing before `_process_queue()`
- `DOMQualityChecker` missing `check_tick`
- `is_trading_allowed(symbol)` signature mismatch
- `RiskEngine.check_all()` missing `sl_pips` and `spread_bps`

Syntax checks passed for:

```powershell
python -m py_compile main.py core\dom_quality.py core\dashboard.py tools\options_iv_scraper.py
```

### 5. IV scraper made more flexible

`tools/options_iv_scraper.py` now supports:

- `IV_API_METHOD`
- `IV_API_BODY_JSON`
- `IV_API_HEADERS_JSON`
- `IV_API_DATA_PATH`
- common IV field names

Still, no real FX options IV/skew source is configured. Do not fake skew.

## Current Runtime State From Last Check

Expected running state:

- `main.py` running
- UDP listening on `0.0.0.0:65000`
- Dashboard listening on `127.0.0.1:8080`
- Live ticks flowing
- L3 scorer warming / warm after enough DOM events
- Recent DB ticks normalized with `bid <= ask`
- No Python traceback in latest run
- No fresh DB lock errors in latest scan

Known remaining non-fatal issues:

- Model drift safety blocks execution.
- IV source still needs a real FX options API if skew/risk reversal is desired.
- Calendar scraper may fail from public sites and use stale/cache fallback.
- FRED can rate limit, but now handles it more gracefully.

## Current Safe Mode

Recommended `.env` mode while collecting real data:

```env
AUTO_EXECUTE=false
MT5_ENABLED=true
GATE_QUICK_REJECT=false
```

Meaning:

- MT5 can be connected.
- Signals can be logged.
- Auto live execution stays off.
- Gates/model still run so `signal_log` grows.

## Commands For The Other Agent To Run

Run from:

```powershell
cd "C:\Users\jogip\OneDrive\Desktop\MY_ORGANIZED_DESKTOP\dfg\urlr"
```

### 1. Read the project context

```powershell
Get-Content AGENTS.md -Tail 140
```

### 2. Syntax check runtime-critical files

```powershell
python -m py_compile main.py core\dom_quality.py core\dashboard.py tools\options_iv_scraper.py
```

### 3. Confirm UDP and dashboard are running

```powershell
Get-NetUDPEndpoint -LocalPort 65000 | Select-Object LocalAddress,LocalPort,OwningProcess
Get-NetTCPConnection -LocalPort 8080 -State Listen | Select-Object LocalAddress,LocalPort,OwningProcess
```

### 4. Confirm dashboard responds

```powershell
$r = Invoke-WebRequest http://127.0.0.1:8080 -UseBasicParsing
"DASHBOARD_OK len=$($r.Content.Length)"
```

### 5. Confirm recent DB ticks are normalized

```powershell
python -c "import sqlite3; c=sqlite3.connect('database/overseer_trades.db'); rows=c.execute(\"select symbol,bid,ask,timestamp from tick_log order by rowid desc limit 20\").fetchall(); print('\\n'.join(f'{s} bid={b} ask={a} {\"OK\" if float(b)<=float(a) else \"CROSSED\"} {t}' for s,b,a,t in rows))"
```

### 6. Scan logs for critical failures

```powershell
Get-ChildItem logs -File | Sort-Object LastWriteTime -Descending | Select-Object -First 5 | ForEach-Object { $_.FullName }
```

Then inspect latest log for:

```text
Traceback
database is locked
DOM quality: crossed_book
Trade blocked by risk limit: drift
```

## What To Do Next To Increase Profit

The next profitable step is not adding more random indicators. The current system already has many gates and institutional-style modules. The key is to make the model learn from real fresh live outcomes.

Recommended order:

1. Keep signal-only mode.
2. Collect 200-500 fresh live `signal_log` outcomes from the normalized Rithmic/MotiveWave feed.
3. Retrain XGBoost on real `signal_log` outcomes.
4. Calibrate per-symbol thresholds separately:
   - `6E` / `6EM6`
   - `6B` / `6BM6`
   - `6J` / `6JM6`
   - `6A` / `6AM6`
   - `6C` / `6CM6`
   - `6N` / `6NM6`
   - `6S` / `6SM6`
   - `GC` / `XAUUSD`
5. Validate BUY and SELL separately.
6. Keep toxic SELL blocks unless fresh live data proves otherwise.
7. Only after drift is healthy, test demo/paper 0.01 lot.

## Prompt For The Other Agent

Use this prompt in the OpenCode session:

```text
Read AGENTS.md first, especially the v12.9.2 Live Handoff section. Then verify the current live OVERSEER state using the commands in opencodecontext.md.

Do not rebuild the project. Do not undo the DOM normalization fix. Do not enable live auto-execution.

Check:
1. main.py process/ports are running.
2. UDP 65000 is active.
3. Dashboard 127.0.0.1:8080 responds.
4. Recent tick_log rows show bid <= ask.
5. Logs have no Traceback, no new database locked errors, and no active DOM crossed_book blocker.
6. Confirm whether the only remaining blocker is model drift safety.

If model drift is blocking, keep AUTO_EXECUTE=false and prepare the next step: collect fresh signal_log outcomes and retrain/calibrate thresholds per symbol. Report exact evidence from DB/logs.
```


## Order Flow Master Reference Matrix

Here is the absolute, definitive master list of **everything** that exists under the umbrella of Order Flow in the OVERSEER architecture.

### Pillar 1: The Raw Structural Components (The Anatomy)
These are the physical, literal elements that make up the market's matching engine at any given microsecond.
* **Passive Liquidity (Limit Orders):** Orders resting in the exchange queue waiting to be hit. They provide a buffer/wall against price movement.
* **Aggressive Volume (Market Orders):** Instant orders that cross the spread to consume passive liquidity. **These are the only orders that move price.**
* **The Bid (Buyers' Queue):** The highest priced passive limit orders currently waiting to buy.
* **The Ask/Offer (Sellers' Queue):** The lowest priced passive limit orders currently waiting to sell.
* **The Spread:** The mathematical gap between the best available Bid and Ask.
* **The Tap/Prints:** The live transaction ledger of matched and finalized buy/sell executions.
* **Queue Position (Price-Time Priority):** Your physical spot in line at a specific price tier within the exchange engine.
* **Market-By-Order (MBO / Level 3 Data):** The raw feed revealing individual order tickets in the queue rather than aggregated numbers.

### Pillar 2: Execution Events & Auction Mechanics (The Friction)
What happens when aggressive volume collides with passive liquidity. This is the behavior traders read to predict the next tick.
* **Absorption:** When a massive passive limit order completely swallows an incoming wave of aggressive market orders, stopping price dead in its tracks.
* **Aggressive Imbalance:** A sudden geometric surge of market buy orders over sell orders (or vice versa) that instantly wipes out a price tier.
* **Slippage:** The physical gap between your requested market price and your actual filled price due to changing liquidity.
* **Liquidity Voids:** Vacuum pockets in the order book where almost no resting limit orders exist, causing price to violently "teleport" through them.
* **Sweeping the Book:** A single, massive market order large enough to instantaneously consume multiple price levels of liquidity at once.
* **Incomplete Auction (Unfinished Business):** When a session or candlestick high/low prints volume at its exact extreme tip, signaling the market must return to properly finish testing that price.
* **Initiative Activity:** Highly motivated market participants pushing price aggressively into completely new value territory.
* **Responsive Activity:** Participants stepping in at extreme highs/lows because they perceive price to be at an unfair premium or discount.

### Pillar 3: Algorithmic & Institutional Footprints (The Manipulation)
Advanced execution tactics used by large institutions and High-Frequency Trading (HFT) systems to mask their true intentions.
* **Iceberg Orders:** A massive order programmatically sliced into tiny, visible pieces so the true size resting in the order book remains hidden.
* **Spoofing:** Fake, massive limit orders placed into the DOM to scare retail traders, only to be automatically canceled a millisecond before execution.
* **Block Trades:** Massive institutional transactions executed outside the public book (Dark Pools) and reported immediately after completion.
* **Stop Hunting (Liquidity Pools):** Engineered price spikes driven by institutions explicitly to trigger clusters of retail stop-losses (which convert to market orders, providing fuel for the institution's entry).
* **Market Maker Inventory Skew:** When liquidity providers rapidly shift their bids or asks to dump exposure after absorbing too many single-sided orders.
* **HFT Arbitrage:** Microsecond-fast bots capturing execution inefficiencies by buying on one exchange and instantly selling on another.

### Pillar 4: The Order Flow Toolset (The Interface)
The specific charting types, software, and mathematical formulas used to visualize the raw engine data listed above.
| Category | Specific Tools & Metrics |
| --- | --- |
| **Visual Charting Engines** | **Footprint / Cluster Charts** (Bid/Ask, Delta, and Volume views)<br><br>**Liquidity Heatmaps** (Visualizes historical limit order thickness over time)<br><br>**Depth of Market (DOM) / Price Ladder** (The real-time execution matrix) |
| **Mathematical Indicators** | **Volume Delta ($Δ$):** $Aggressive Buys - Aggressive Sells$<br><br>**Cumulative Delta:** The running session total of Net Delta<br><br>**Volume Profile / TPO:** Volume tracked horizontally by price node<br><br>**VWAP:** Volume-Weighted Average Price |
| **Algorithmic Monitors** | **Speed of Tape (Ticks per Second):** Measures execution velocity<br><br>**Large Trade Identifiers / Block Trackers:** Filters out noise to show institutional transactions<br><br>**Iceberg Detectors:** Automated software flags that track hidden passive reloading |
| **Core Software Engines** | **Sierra Chart, Bookmap, ATAS, Jigsaw Trading, QuantTower, NinjaTrader** |
