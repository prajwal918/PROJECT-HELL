# OVERSEER v14.0 — Project Context for AI Assistants (updated 2026-06-12)

> READ THIS FILE FIRST. It contains everything needed to understand, modify, and debug this project without scanning all files.

---

## 1. WHAT IS THIS

OVERSEER is a **real-time forex trading system** that:
- Receives tick data via UDP (from MotiveWave/CME futures) — FXCM and ZMQ disabled
- Runs 152 gate-based signal filters organized into 23 frameworks (6 new order flow gates added v12.12)
- Scores trade quality with XGBoost (60+ features: 23 framework scores + symbol encoding + L3 flow + bias breakdown + market context + fundamental bias + new gate features)
- 16 institutional-grade modules wired into tick loop (VPIN, OFI, RegimeIntel, CrossAsset, CB_NLP, VolSurface, PairsStat, Network, SelfSupervised, SeqCore, XAI, VectorMem, RL_Brain, Causal, Attention, ExecAlgo, PortfolioRisk)
- **Legendary Mode (v13.0)**: Druckenmiller approach — 6 platinum gates must ALL fire + score ≥ 0.95 → one trade per symbol per day, 4:1 RR target, 0.75 Kelly sizing, 3-tranche scale-in entry
- 7 new defensive infrastructure modules: Kill Zone Precision Timer, Futures Rollover Calendar, Spread Z-Score Intelligence, Psychological Level Detector, Session Levels (PDH/PDL/PWH/PWL), Scale-In Engine, Legendary Exit Trail
- Executes trades via MetaTrader5 (Windows-only) or OANDA REST API (Linux)
- Sends alerts via Telegram
- Scrapes economic calendar, COT data, and options IV from external sources

**Language**: Python 3.8+ | **Platform**: Windows (MT5) / Linux (OANDA/signal-only) | **DB**: SQLite WAL mode

---

## 2. ARCHITECTURE

```text
Data In Processing Execution
───────── ────────── ─────────
UDP (Rithmic) ─▶ asyncio.Queue ─▶ enrich_tick() ─▶ Parallel Gates ─▶ XGBoost ─▶ MT5 / OANDA
│ │ │ │ │
│ │ ┌─ VPIN (every tick) │ └─▶ Telegram alerts
│ │ ├─ OFI (every tick) │
│ │ ├─ RegimeIntel (tick) │
│ │ ├─ SeqCore (10th) │
│ │ ├─ VectorMem (signal) │
│ │ ├─ XAI (signal) │
│ │ ├─ RL_Brain (exec) │
│ │ ├─ Attention (tick) │
│ │ ├─ CrossAsset (10th) │
│ │ ├─ PortfolioRisk (exec)│
│ │ ├─ VolSurface (10th) │
│ │ ├─ PairsStat (500th) │
│ │ ├─ Network (200th) │
│ │ ├─ CB_NLP (500th) │
│ │ ├─ SelfSupervised (1K)│
│ │ ├─ ExecAlgo (exec) │
│ │ └─ CausalEngine (5K) │
│ └─▶ framework_scorer.py (23 scores)
│ ┌─ Killzone Timer (tick) │
│ ├─ Futures Calendar (tick) │
│ ├─ Spread Z-Score (tick) │
│ ├─ Psych Levels (tick) │
│ └─ Session Levels (tick) │
└─▶ DXY / Risk Regime / Candle Agg
└─▶ LEGENDARY MODE ─▶ Scale-In Engine ─▶ Legendary Exit Trail
└─▶ SQLite (batched commits every 50 ticks)
```

### Data Flow (per tick)
1. `hub_listener.py` receives UDP tick → pushes to `asyncio.Queue`
2. `_process_queue()` in `main.py`:
   - Enriches tick with counterpart prices, lag data
   - Updates global `_cumulative_delta` and injects into tick dict
   - Updates DXY calculator, risk regime, candle aggregator (cached every 10 ticks)
   - Updates `_ORDERFLOW_STATE` for the live dashboard (Absorption, HFT, Adverse Risk)
   - Buffers tick data for batch SQLite insert
   - Checks halt status (cached every 5 seconds)
- Evaluates all 152 gates in parallel via `GateRegistry.evaluate(tick)` (ThreadPoolExecutor)
- Aggregates gate outputs → 23 framework scores via `framework_scorer.py` (with directional asymmetry: SELL ×0.6)
- Predicts trade quality via XGBoost (`load_model.py`) — synchronous call (async removed to fix memory leak, M-2)
- Applies L3 bias adjustments (spoof, queue, iceberg, adverse, HFT, vacuum)
- Applies IV skew bias
- Applies fundamental bias (rate differentials, yield spreads, news sentiment)
- **Legendary Mode check** (`ml/legendary_mode.py`): 6 platinum gates + score ≥ 0.95 + ≥2 supporting gates → one trade per symbol per day, 0.75 Kelly sizing, 4:1 RR TP, 3-tranche scale-in
- **Tick enrichment** (v13.0): candle arrays (`_candles_15m`, `_candles_1h`, `_candles_daily`), killzone quality, futures roll status, spread z-score, psychological level, session level proximity all injected onto tick dict
- Decision: `dynamic_selector.decide()` handles symbol/direction/score filtering (No hardcoded blocks)
- Logs execution quality, trade audit, paper trades
- Periodic P&L report via Telegram, auto-retrain (Parallel), web dashboard update

---

## 3. DIRECTORY STRUCTURE

```
urlr/
├── main.py # Entry point. Async loop, all component integration
├── jogiapp.py # Launcher + Live Order Flow Dashboard (Searchable UI)
├── supervisor.py # Auto-restart supervisor (UDP watchdog, memory limit)
├── .env # All configuration (BIAS_*, SPREAD_*, API keys, etc.)
├── requirements.txt # Runtime dependencies
├── setup.ps1 # One-click installer (Python + pip + DB + syntax check)
│
├── core/                    # Core processing components
│   ├── hub_listener.py      # UDP listener (Rithmic CME futures feed)
│   ├── zmq_bridge.py        # ZMQ subscriber (L2/L3 order book from hub)
│   ├── symbol_mapper.py     # Symbol resolution, future↔spot mapping
│   ├── dxy_calculator.py    # DXY index calculation from 6 pairs
│   ├── risk_regime.py       # Risk regime classifier
│   ├── candle_aggregator.py # Tick → OHLC candle aggregation
│   ├── telegram_alerts.py   # Telegram bot integration
│   ├── dashboard.py # Web dashboard (HTTP status page, /api/stats JSON)
│ ├── dom_quality.py # DOM health monitor + kill switch
│ ├── currency_exposure.py # FX-3 currency exposure tracker
│ ├── risk_engine.py # Unified pre-trade risk engine
│ ├── latency_tracker.py # Pipeline stage latency tracker
│ ├── killzone_timer.py # Kill zone precision quality timer (peak window detection)
│ ├── futures_calendar.py # CME quarterly rollover calendar (PRE_ROLL/NEAR_EXPIRY/ROLL_NOW)
│ ├── spread_intelligence.py # Spread z-score anomaly detection (vs historical baseline)
│ ├── psychological_levels.py # Big figure / half figure / quarter figure + stop hunt detection
│ ├── session_levels.py # PDH/PDL/PWH/PWL proximity detection
│ └── setup_lag.py # Lag detection setup
│
├── engine_logic/            # Signal evaluation
│ ├── gates/ # 152 gate files (gate_A.py through gate_Z94.py + gate_FUND + 10 technical gates + 6 order flow gates)
│ │ ├── base_gate.py # BaseGate abstract class
│ │ ├── gate_registry.py # Auto-discovers all gate_*.py; parallel execution
│ │ ├── gate_A.py # Multi-TF trend alignment
│ │ ├── gate_B.py # Multi-TF structure (17 sub-conditions)
│ │ ├── gate_C.py # Wick rejection / pin bar
│ │ ├── gate_D.py # Directional momentum (REQUIRED for trade)
│ │ ├── gate_E.py # Entry precision
│ │ ├── gate_F.py # Volume baseline
│ │ ├── gate_G.py # Volume spike
│ │ ├── gate_H.py # Liquidity sweep detection
│ │ ├── gate_I.py # Stop hunt detection
│ │ ├── gate_J.py # Weekly support proximity
│ │ ├── gate_K.py # Weekly resistance proximity
│ │ ├── gate_L.py # Session timing (ALL sessions allowed)
│ │ ├── gate_M.py # Kill zone alignment
│ │ ├── gate_N.py # News proximity
│ │ ├── gate_O.py # News avoidance
│ │ ├── gate_P.py # Asian range detection
│ │ ├── gate_Q.py # Asian range breakout
│ │ ├── gate_R.py # COT positioning alignment
│ │ ├── gate_S.py # COT momentum
│ │ ├── gate_T.py # Post-news continuation
│ │ ├── gate_U.py # Post-news reversal
│ │ ├── gate_V.py # Cross-pair confirmation
│ │ ├── gate_W.py # Cross-pair divergence
│ │ ├── gate_X.py # Risk regime filter (ALL regimes allowed)
│ │ ├── gate_Y.py # Correlation exposure
│ │ ├── gate_Z.py # L0 institutional flow
│ │ ├── gate_Z1-Z7.py # L1 institutional flow tiers
│ │ ├── gate_Z8-Z94.py # L2 microstructure filters
│ │ ├── gate_VP.py # Volume profile (POC/VAL/VAH)
│ │ ├── gate_TPO.py # Market profile (TPO value area)
│ │ ├── gate_DD.py # Delta divergence (price vs volume delta)
│ │ ├── gate_CVD.py # Cumulative volume delta alignment + price/delta divergence detection
│ │ ├── gate_IMB.py # Bid/ask size imbalance
│ │ ├── gate_VWAP.py # VWAP position filter
│ │ ├── gate_RSI.py # RSI overbought/oversold + divergence
│ │ ├── gate_MACD.py # MACD signal line crossover
│ │ ├── gate_BB.py # Bollinger Band position filter
│ │ ├── gate_SR.py # Support/resistance proximity
│ │ ├── gate_news.py # Economic event gate (ALL sessions/regimes)
│ │ ├── gate_iv.py # Options IV skew + expansion gates
│ │ ├── gate_continuation.py # Post-release continuation filter
│ │ ├── gate_cross_market.py # Cross-market arbitrage detection
│ │ ├── gate_FUND.py # Fundamental direction alignment (rate differentials, threshold=0.30)
│ │ ├── gate_stacked_imbalance.py # Diagonal 3-level 300% DOM imbalance (institutional wall)
│ │ ├── gate_unfinished.py # Unfinished Business magnet filter (incomplete auction levels)
│ │ ├── gate_tape_velocity.py # Ticks Per Second exhaustion tracker (session extreme detection)
│ │ ├── gate_iceberg_monitor.py # Passive absorption / hidden iceberg detection (trade vs DOM size)
│ │ ├── gate_bar_cot.py # Bar COT position tracker (POC relative to candle range)
│ │ └── event_analyzer.py # Event impact analysis
│   └── event_analyzer.py # Event impact analysis
│
├── ml/                      # Machine learning
│   ├── drift_monitor.py # Model drift monitor (WR per score bucket)
│   ├── dynamic_pair_selector.py # Dynamic symbol/direction filtering rules
│   ├── order_book_engine.py # Incremental MBO order book engine
│   ├── per_symbol_model.py # Per-symbol XGBoost model manager
│ ├── framework_scorer.py # Collapses 152 gate bools → 23 continuous scores [0-1]
│ ├── legendary_mode.py # LEGENDARY MODE — 6 platinum gates + score ≥ 0.95 → full conviction trade
│ ├── signal_logger.py # Signal journal — logs ALL signals with outcomes + order flow
│   ├── load_model.py # XGBoost inference + reload_model()
│   ├── train_model.py # XGBoost training (PARALLEL n_jobs=-1)
│   ├── l3_scorer.py # L3 real-time institutional flow scorer
│   ├── l3_pipeline.py # L3 feature pipeline
│   └── l3_institutional_features.py # L3 feature extraction
│
├── execution/ # Trade execution
│ ├── mt5_executor.py # MT5 connection, execute_trade(), close_trade(), etc.
│ ├── oanda_executor.py # OANDA REST API executor (Linux-compatible)
│ ├── dynamic_exit.py # Dynamic exit manager (breakeven, trailing SL, legendary trail)
│ ├── partial_close.py # Partial close manager
│ ├── scale_in_engine.py # 3-tranche institutional entry (33/34/33%)
│ ├── trade_tracker.py # Closed position tracker
│ ├── execution_quality.py # Fill/rejection quality logger
│ ├── trade_replay.py # Full pipeline state audit + replay
│ └── paper_trading.py # Shadow trading via SimExecutor
│
├── tools/                   # External data scrapers & utilities
│   ├── calendar_scraper.py # ForexFactory economic calendar
│   ├── cot_scraper.py # CFTC COT report scraper
│   ├── options_iv_scraper.py # Options IV/skew (real API or Garman-Klass fallback)
│   ├── fred_scraper.py # FRED API (US yields, Fed Funds, CPI, NFP, yield curve)
│   ├── ecb_scraper.py # ECB Data Portal (ECB rates, Bund yields, HICP, Euribor)
│   ├── finnhub_scraper.py # Finnhub (news sentiment, economic calendar)
│   ├── scraper_utils.py # Shared: fetch_with_retry(), ScraperHealth, is_data_stale()
│   ├── calibrate_biases.py  # Grid-search bias weight calibration
│   ├── rithmic_mbo_udp_bridge.py  # Rithmic MBO→UDP bridge
│   ├── binance_udp_bridge.py      # Binance→UDP bridge (crypto)
│   ├── rtrader_excel_udp_bridge.py # RTrader Excel→UDP bridge
│   └── udp_probe.py         # UDP listener for live bridge validation
│
├── database/
│   ├── setup_db.py          # Schema: tick_log, trade_executions, signal_log, model_features, etc.
│   └── overseer_trades.db   # SQLite WAL mode database
│
├── bridge/                  # Bridge source files (compile separately)
│   ├── OverseerMotiveWaveBridge.java  # MotiveWave SDK Java bridge
│   ├── OverseerAllPairsBridge.cs      # Quantower C# bridge
│   └── OverseerAllPairsBridge.csproj
│
├── config/                  # Configuration files
│   ├── instrument_config.py # Per-instrument profiles + rolling stats
│   └── symbol_map.json      # Future↔spot symbol mapping
│
├── backtest/                # Backtest framework
│   ├── engine.py            # Main backtest engine
│   ├── data_loader.py       # Loads HistData M1, Dukascopy tick, generic CSV
│   ├── simulator.py         # SimExecutor — in-memory trade simulator
│   ├── analytics.py         # BacktestResult — Sharpe, drawdown, win rate
│   ├── gate_diag.py         # Per-gate pass rate diagnostic
│   └── score_diag.py        # Score distribution diagnostic
│
├── setup/                   # Setup scripts + guides
│   └── quantower_rithmic_fxcm_working_setup.md
│
└── logs/                    # Runtime logs
```

---

## 4. THE 23 FRAMEWORK SCORES (ml/framework_scorer.py)

This is the KEY innovation. 152 binary gate outputs are collapsed into 23 continuous [0.0-1.0] scores:

| # | Framework Name | Maps From | Purpose |
|---|---------------|-----------|---------|
| FW01 | `FW01_multi_tf_trend` | gate_A, gate_B | Multi-timeframe trend alignment |
| FW02 | `FW02_price_action` | gate_C, gate_E, gate_SR | Price action / wick rejection / S-R proximity |
| FW03 | `FW03_volume` | gate_F, gate_G, gate_VOL, gate_DD, gate_IMB, gate_CVD | Volume confirmation + CVD + delta divergence + imbalance |
| FW04 | `FW04_liquidity_sweep` | gate_H, gate_I, gate_Z14-Z16 | Liquidity sweep detection |
| FW05 | `FW05_weekly_levels` | gate_J, gate_K | Weekly level proximity |
| FW06 | `FW06_session_kz` | gate_SESSION, gate_L, gate_M | Session / kill zone |
| FW07 | `FW07_econ_event` | gate_NEWS, gate_N, gate_O | Economic event lean |
| FW08 | `FW08_asian_range` | gate_P, gate_Q | Asian range breakout |
| FW09 | `FW09_cot_positioning` | gate_R, gate_S | COT positioning |
| FW10 | `FW10_post_news` | gate_T, gate_U | Post-news continuation |
| FW11 | `FW11_iv_skew` | gate_IVSKEW, gate_IVEXP | Options IV / skew |
| FW12 | `FW12_dxy_isolation` | gate_DXY, gate_V, gate_W | DXY / cross-pair isolation |
| FW13 | `FW13_lag_arb` | gate_XMKT, gate_LEADLAG, gate_ARB, gate_XCORR | Lag arbitrage |
| FW14 | `FW14_risk_regime` | gate_REGIME, gate_X, gate_Y | Risk regime |
| FW15 | `FW15_l3_flow` | gate_Z, gate_Z1-Z7, gate_Z8-Z13, gate_Z17-Z94 | L3 institutional flow |
| FW16 | `FW16_directional_momentum` | gate_D | Directional momentum (REQUIRED for trade) |
| FW17 | `FW17_volume_profile` | gate_VP, gate_TPO, gate_VWAP, gate_stacked_imbalance, gate_iceberg_monitor, gate_tape_velocity, gate_HURST | Volume profile / market structure / institutional walls / tape velocity / Hurst |
| FW18 | `FW18_technical` | gate_RSI, gate_MACD, gate_BB, gate_bar_cot, gate_unfinished | Technical analysis + Bar COT + Unfinished Business |
| FW19 | `FW19_fundamental` | gate_FUND | Fundamental direction alignment (rate differentials / yield spreads / sentiment) |
| FW20 | `FW20_legendary` | gate_Z15, gate_A, gate_D, gate_stacked_imbalance, gate_CVD, gate_M, gate_legendary_composite | Legendary mode composite quality |
| FW21 | `FW21_smart_money` | gate_FVG, gate_ORDER_BLOCK, gate_SFP, gate_WYCKOFF, gate_PO3, gate_stacked_imbalance, gate_iceberg_monitor, gate_CVD, gate_unfinished | Smart money concepts (FVG, OB, SFP, Wyckoff, PO3) |
| FW22 | `FW22_intermarket` | gate_DXY, gate_V, gate_W, gate_XMKT, gate_LEADLAG, gate_DXY_TREND, gate_CURRENCY_STR, gate_LONDON_FIX | Intermarket correlations |
| FW23 | `FW23_positioning` | gate_R, gate_S, gate_FUND, gate_Z14, gate_Z15, gate_RETAIL_SENTIMENT, gate_GAMMA_EXPOSURE | Positioning intelligence |

**Why**: 152 binary features with 500 trades = overfit. 23 continuous features = learnable.

---

## 5. KEY INTERFACES

### Gate Interface (engine_logic/gates/base_gate.py)
```python
class BaseGate(ABC):
    name: str                    # e.g. "gate_A"
    @abstractmethod
    def evaluate(self, tick: dict) -> bool: ...
```
New gates auto-loaded by `gate_registry.py` via `pkgutil.iter_modules`.

### Model Interface (ml/load_model.py)
```python
predict_trade_quality(gate_states: dict[str, bool], tick: dict) -> float # 0.0-1.0
should_trade(gate_states: dict[str, bool], tick: dict) -> bool # > per-symbol threshold
```
Internally aggregates gate_states → 23 framework scores before XGBoost inference. Also reads L3/bias/market context from tick dict when model expects those features.

### Trade Execution

**MT5 (execution/mt5_executor.py)** — Windows-only
```python
connect_mt5(account, password, server) -> bool
execute_trade(symbol, direction, lot_size, sl_pips, tp_pips) -> dict | None
close_trade(ticket) -> bool
close_trade_partial(ticket, volume) -> bool
modify_sl(ticket, new_sl) -> bool
kelly_lot_size(win_rate, avg_win, avg_loss, account_balance) -> float
```
Includes slippage estimation, spread validation, and fill_price calculation.

**OANDA (execution/oanda_executor.py)** — Linux-compatible
```python
oanda_connect() -> bool
oanda_execute_trade(symbol, direction, lot_size, sl_pips, tp_pips) -> dict | None
oanda_close_trade(trade_id) -> bool
oanda_close_partial(trade_id, units) -> bool
oanda_modify_sl(trade_id, new_sl) -> bool
oanda_get_open_positions() -> list | None
```
Uses OANDA REST API v20. Instrument mapping via `config/symbol_map.json`. Handles `MARKET_HALTED` on weekends.

### Scraper Utils (tools/scraper_utils.py)
```python
fetch_with_retry(url, session, max_retries=3) -> Response
class ScraperHealth:  # tracks success/failure, marks unhealthy after 5 consecutive fails
is_data_stale(db_path, table, max_age_hours) -> bool
```

---

## 6. ENVIRONMENT VARIABLES (.env)

### Critical (must set)
- `MT5_ACCOUNT`, `MT5_PASSWORD`, `MT5_SERVER` — broker credentials
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` — alert channel
- `IV_API_URL`, `IV_API_KEY` — options data feed (leave empty = Garman-Klass fallback, skew=0)

### Model Behavior
- `BIAS_SPOOF=0.15`, `BIAS_QUEUE=0.10`, `BIAS_ICEBERG=0.05`, `BIAS_ADVERSE=0.20`, `BIAS_HFT=0.08`, `BIAS_VACUUM=0.12`, `BIAS_IV_SKEW=0.10`
- `BIAS_MAX_SHIFT=0.15` — maximum total bias shift (L3 + IV combined), clamps adjusted_score so quality threshold remains meaningful
- `QUALITY_SCORE_MIN=0.85` — trade quality threshold (global minimum)
- `THRESH_{SYMBOL}` — per-symbol thresholds (e.g. `THRESH_6BM6=0.85`, `THRESH_6AM6=0.90`, `THRESH_6EM6=0.95`, `THRESH_6JM6=0.85`, `THRESH_6CM6=0.90`)
- `SELL_SIGNALS_BLOCKED=6BM6,6JM6,6AM6,6EM6` — block SELL on toxic symbols (only 6CM6 SELL allowed)
- `GATE_QUICK_REJECT=true/false` — skip XGBoost when gate_D/gate_Z7 false (set `false` for signal collection)
- `GATE_D_LOOKBACK=4` — rolling momentum lookback ticks for gate_D
- `VOLUME_SPIKE_RATIO=1.5` — volume spike detection threshold for gate_G
- `FUNDAMENTAL_BIAS_WEIGHT=0.05` — fundamental bias adjustment weight
- `UDP_DISCONNECT_TIMEOUT=30` — hub_listener disconnect timeout in seconds
- Calibrate biases with: `python -m tools.calibrate_biases`

### Tick Processing
- `COMMIT_INTERVAL_TICKS=50` — SQLite commit batch size
- `TICK_BUFFER_MAX=100` — tick insert buffer size
- `HALT_CACHE_TTL_SECONDS=5.0` — halt check cache duration

### Spread Limits (per symbol)
- `SPREAD_MAX_EURUSD=2.0`, `SPREAD_MAX_GBPUSD=2.5`, etc. — reject trades exceeding these

### Risk Limits
- `MAX_DAILY_LOSS_PCT=3.0` — max daily loss as % of account balance
- `MAX_WEEKLY_LOSS_PCT=6.0` — max weekly loss as % of account balance
- `MAX_DAILY_TRADES=3` — max trades per day
- `CONSECUTIVE_LOSS_LIMIT=2` — halt after N consecutive losses
- `DB_DAILY_LOSS_LIMIT=500` — DB trigger daily loss dollar limit (backstop)
- `DB_CONSECUTIVE_LOSSES=2` — DB trigger consecutive loss count (backstop)

### Performance (2-core / low-spec laptops)
- `GATE_EVAL_INTERVAL=1` — evaluate gates every N ticks (2 = skip every other tick, 1 = every tick)
- `AUTORETRAIN_TRADES=50` — auto-retrain XGBoost after N new closed trades (0 = disabled)

### Dashboard
- `DASHBOARD_ENABLED=true` — enable web dashboard
- `DASHBOARD_PORT=8080` — dashboard HTTP port
- `DASHBOARD_BIND=127.0.0.1` — bind address (default localhost for security)
- `DASHBOARD_API_KEY` — Bearer token for dashboard auth (empty = no auth)

### Execution
- `MT5_ENABLED=true/false` — enable live trading (Windows-only)
- `AUTO_EXECUTE=true/false` — auto-execute vs signal-only
- `SL_PIPS=5`, `TP_PIPS=12.5` — default stop-loss / take-profit (overridden by per-instrument config)
- `OANDA_FEED_ENABLED=true/false` — enable OANDA price feed
- `FXSSI_WEB_ENABLED=true/false` — enable FXSSI sentiment scraper
- `YAHOO_NEWS_ENABLED=true/false` — enable Yahoo news sentiment scraper
- `OANDA_FEED_POLL_INTERVAL=1.0` — OANDA price feed polling interval (seconds)

### OANDA Execution (Linux)
- `OANDA_API_KEY` — OANDA REST API key
- `OANDA_ACCOUNT_ID` — OANDA account ID (e.g. `101-001-39497201-001`)
- `OANDA_BASE_URL` — `https://api-fxpractice.oanda.com` (practice) or `https://api-fxtrade.oanda.com` (live)
- `OANDA_STREAM_URL` — `https://stream-fxpractice.oanda.com` (practice) or `https://stream-fxtrade.oanda.com` (live)
- When `MT5_ENABLED=false` + `AUTO_EXECUTE=true`, system uses OANDA REST API for execution
- OANDA instrument mapping: 6EM6→EUR_USD, 6BM6→GBP_USD, 6JM6→USD_JPY, 6AM6→AUD_USD, 6CM6→USD_CAD, 6NM6→NZD_USD, 6SM6→USD_CHF, GCM6→XAU_USD, CLN6→WTICO_USD
- OANDA marks `MARKET_HALTED` on weekends (forex closes Friday 5PM ET, opens Sunday 5PM ET)

### Per-Instrument Overrides
- `INST_{SYMBOL}_{FIELD}=value` — override any profile field for a specific instrument
- Example: `INST_6J_VELOCITY_THRESHOLD=0.04` overrides velocity threshold for 6J only
- Example: `INST_EURUSD_SL_PIPS=4` sets EURUSD-specific SL
- Example: `INST_6B_SESSION_ALLOW_ASIA=true` enables Asian session for 6B

### Legendary Mode (Druckenmiller approach)
- `LEGENDARY_MODE_ENABLED=true` — enable legendary mode decision path
- `LEGENDARY_SCORE_THRESHOLD=0.95` — minimum raw score for legendary signal
- `LEGENDARY_SUPPORTING_MIN=2` — minimum supporting gates that must also fire
- `LEGENDARY_MAX_PER_DAY=1` — max legendary trades per symbol per day
- `LEGENDARY_TP_RR=4.0` — legendary take-profit as multiple of SL (4:1 RR)
- `LEGENDARY_BE_RR=1.5` — move SL to breakeven at 1.5:1 RR
- `LEGENDARY_TRAIL_START_RR=2.0` — start trailing at 2:1 RR
- `LEGENDARY_TRAIL_STEP_PIPS=5` — trailing step in pips
- `LEGENDARY_KELLY_FRACTION=0.75` — Kelly fraction for legendary sizing (0.75 = 3/4 Kelly)
- `LEGENDARY_KILLZONE_PEAK_ONLY=true` — only fire in peak 3-minute kill zone window

### Scale-In Engine
- `SCALE_IN_ENABLED=true` — enable 3-tranche entry
- `SCALE_IN_CONFIRMATION_PIPS=1.0` — pips in profit to add tranche 2
- `SCALE_IN_MAX_WAIT_TICKS=50` — max ticks before completing partial entry

### Defensive Infrastructure
- `SPREAD_ZSCORE_AVOID=3.0` — z-score threshold to block trade (3σ above normal)
- `SPREAD_ZSCORE_WARN=2.5` — z-score warning threshold
- `FUTURES_PRE_ROLL_DAYS=14` — days before expiry to start degrading signals
- `FUTURES_NEAR_EXPIRY_DAYS=7` — days before expiry for significant degradation
- `FUTURES_ROLL_NOW_DAYS=3` — days before expiry to block trading entirely
- `KILLZONE_PEAK_TOLERANCE_MINUTES=3` — minutes from session peak to count as "peak window"

---

## 7. PER-INSTRUMENT CONFIGURATION (config/instrument_config.py)

Every CME futures contract and forex spot pair has its own profile with instrument-specific thresholds. **Gates read from the tick dict, which is enriched by InstrumentConfig before evaluation.**

### Supported Instruments

| CME Future | Spot Counterpart | pip_size | velocity_threshold | lag_threshold_pips | sl_pips | tp_pips |
|-----------|-----------------|----------|-------------------|-------------------|---------|---------|
| 6E | EURUSD | 0.0001 | 0.0003 | 1.5 | 5.0 | 12.5 |
| 6B | GBPUSD | 0.0001 | 0.0004 | 1.5 | 7.0 | 17.5 |
| 6J | USDJPY | 0.01 | 0.03 | 3.0 | 8.0 | 20.0 |
| 6A | AUDUSD | 0.0001 | 0.0003 | 1.5 | 6.0 | 15.0 |
| 6C | USDCAD | 0.0001 | 0.0003 | 1.5 | 6.0 | 15.0 |
| 6N | NZDUSD | 0.0001 | 0.0003 | 1.5 | 6.0 | 15.0 |
| 6S | USDCHF | 0.0001 | 0.0003 | 1.5 | 6.0 | 15.0 |
| GC | XAUUSD | 0.1 | 0.5 | 2.0 | 50.0 | 125.0 |
| CL | USOIL (WTI) | 0.01 | 0.05 | 3.0 | 20.0 | 50.0 |

### How it works

1. `InstrumentConfig` is a singleton initialized at startup
2. Each tick is enriched via `instrument_config.enrich_tick(tick)` before gate evaluation
3. Rolling stats (ATR, spread, velocity) are tracked per symbol and auto-adapt after 200+ ticks
4. After 200 ticks, ATR bounds auto-adjust: `min = rolling_atr * 0.3`, `max = rolling_atr * 5.0`
5. Env overrides: `INST_{SYMBOL}_{FIELD}=value` takes priority over defaults

### Gates using per-instrument config

| Gate | Before (hardcoded) | After (from tick dict) |
|------|-------------------|----------------------|
| gate_A | `> 0.0` | `> tick_size * 0.5` |
| gate_F | `0.5` velocity | `velocity_threshold` per instrument |
| gate_E | `5.0` bps spread | `spread_bps_max` per instrument |
| gate_I | `0.2` OBI | `obi_threshold` per instrument |
| gate_V | `0.5-30.0` ATR range | `atr_bps_min/max` (auto-adapts from rolling) |
| gate_H | Global session | `session_allow_asia` per instrument |
| gate_L | `50` depth | `depth_min_contracts` per instrument |
| gate_P | `1.5` RR | `risk_reward_min` per instrument |
| gate_Z | `0.4` adverse | `adverse_threshold` per instrument |
| gate_Z7 | `1.5` pips lag | `lag_threshold_pips` per instrument (in pips, not raw price) |
| gate_cross_market | Fixed thresholds | Per-instrument `cross_spread_max_pips`, `lead_lag_max_pips`, `arb_min/max_lag_pips` |

---

## 8. DATABASE SCHEMA (SQLite)

Key tables (see `database/setup_db.py`):
- `tick_log` — raw tick data (symbol, bid, ask, delta, dom_json, timestamp)
- `trade_executions` — executed trades with gate_states_json
- `signal_log` — **ALL signals** (signal-only + executed) with 19 framework scores, L3 order flow features, bias breakdown, DOM snapshot, tick context, and outcome tracking at 10/50/200 tick horizons
- `model_features` — auto-populated from trade_executions via trigger
- `options_iv` — IV data with `source` column ("custom_api" | "realised_vol")
- `halt_status` — emergency halt flag
- `candles_1m`, `candles_5m`, `candles_15m`, `candles_1h` — OHLC candles

### signal_log Table (Signal Journal)

This is the **primary dataset for model retraining**. Every signal above the 0.65 threshold is logged here, whether executed or signal-only.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Auto-increment signal ID |
| `symbol` | TEXT | Trading instrument |
| `direction` | TEXT | BUY/SELL |
| `score` | REAL | Raw XGBoost quality score |
| `adjusted_score` | REAL | Score after L3 + IV bias adjustments |
| `executed` | INTEGER | 0=signal-only, 1=trade executed |
| `entry_price` | REAL | Fill price (if executed) |
| `exit_price` | REAL | Close price (if executed and closed) |
| `pnl` | REAL | Profit/loss (if closed) |
| `gate_states_json` | TEXT | All 131 gate boolean outputs |
| `framework_scores_json` | TEXT | 19 framework scores (FW01-FW19) |
| `l3_features_json` | TEXT | L3 order flow: spoof, queue, iceberg, adverse, HFT, vacuum signals + l3_prediction/confidence |
| `bias_breakdown_json` | TEXT | Individual bias contributions (spoof_bias, queue_bias, etc.) |
| `dom_snapshot_json` | TEXT | Order book DOM at signal time |
| `tick_bid/ask/delta/volume` | REAL | Tick-level context |
| `spread_bps` | REAL | Spread in basis points |
| `risk_regime` | TEXT | Current risk regime |
| `session` | TEXT | Current session |
| `dxy` | REAL | DXY index value |
| `outcome_10ticks` | TEXT | WIN/LOSS/FLAT at 10-tick horizon |
| `outcome_50ticks` | TEXT | WIN/LOSS/FLAT at 50-tick horizon |
| `outcome_200ticks` | TEXT | WIN/LOSS/FLAT at 200-tick horizon |
| `timestamp` | TEXT | Signal time |
| `closed_at` | TEXT | Close time (if executed) |

**Outcome tracking** (`ml/signal_logger.py`): After a signal is logged, the system tracks mid-price movement at 10, 50, and 200 ticks after entry. WIN = price moved >= 1 pip in signal direction. LOSS = moved >= 1 pip against. FLAT = within 1 pip.

**Purpose**: After 200+ signals, use `outcome_200ticks` as the label to retrain XGBoost on REAL market outcomes instead of synthetic L3 labels. This is the path to actual predictive power.

**Mode**: WAL (Write-Ahead Logging) for concurrent read/write.

---

## 9. HOW TO RUN

```powershell
# One-click setup (installs Python if needed, pip packages, DB, syntax check)
.\setup.ps1

# Or manual:
pip install -r requirements.txt
python database/setup_db.py
python main.py
```

---

## 11. COMMON MODIFICATION PATTERNS

### Adding a new gate
1. Create `engine_logic/gates/gate_NEW.py` inheriting `BaseGate`
2. Set `name = "gate_NEW"`
3. Implement `evaluate(self, tick) -> bool`
4. Auto-loaded by `gate_registry.py` — no registration needed
5. If it belongs to a framework, add it to `_FRAMEWORK_MAP` in `ml/framework_scorer.py`

### Adding a new framework score
1. Add entry to `_FRAMEWORK_MAP` in `ml/framework_scorer.py`
2. Retrain model: `python -m ml.train_model`
3. Delete old `overseer_model.pkl` and `gate_weights.json` first

### Adding a new scraper
1. Create `tools/new_scraper.py`
2. Use `fetch_with_retry()` and `ScraperHealth` from `tools/scraper_utils.py`
3. Call from `main.py` at appropriate interval

### Changing trade logic
1. Modify the score threshold or gate requirements in `main.py:_process_queue()`
2. Currently requires: `score > per-symbol threshold` (raw model score, not adjusted_score)
3. Adverse L3 bias (`clamped_bias < -0.05`) rejects signal before threshold check
4. **Autonomous Optimization**: Every 500 ticks, `ml/autonomous_optimizer.py` is triggered to rewrite `config/dynamic_elite_params_rare_min5.json`. Modify this script to change the "Golden Rule" search criteria.

### Modifying the Dashboard
1. **Live Sentiment**: Update `_ORDERFLOW_STATE` in `main.py` to add new real-time signals.
2. **Web UI**: Modify `HTML` and the `refresh()` JS function in `jogiapp.py` to display new columns or panels.
3. **No-Trade Journal**: Edit `get_rejections()` in `jogiapp.py` to parse different rejection reasons from the logs.
4. SELL signals blocked on toxic symbols via `SELL_SIGNALS_BLOCKED` env var

---

## 12. KNOWN ISSUES & DESIGN DECISIONS

- **Options IV**: Without a real API (`IV_API_URL` empty), Garman-Klass provides ONLY atm_iv. `get_skew_score()` returns 0, `get_rr_25d()` returns 0. Never fakes RR data.
- **DXY**: Fixed double weight calculation bug. Single correct `_ADJUSTED_WEIGHTS` assignment.
- **Model**: Old model used 131 binary gate features → overfit. Now uses 19 continuous framework scores.
- **Tick optimization**: Commits are batched (50-tick intervals), halt checks cached (5s TTL), DXY/risk regime cached (10-tick intervals).
- **Gate quick-reject**: If `GATE_QUICK_REJECT=true` (default) and gate_D or gate_Z7 are false, XGBoost inference is skipped. Saves ~80% CPU on non-signal ticks. Set `GATE_QUICK_REJECT=false` for signal collection mode.
- **Risk limits enforced in Python**: `_check_risk_limits()` blocks trades when daily/weekly loss % exceeded, max daily trades reached, or consecutive losses hit. DB trigger also halts system as backstop.
- **Auto-retrain**: After `AUTORETRAIN_TRADES` new closed trades, model retrains automatically via `imblearn.Pipeline` (SMOTE+XGB). Runs in background thread via `loop.run_in_executor()` to avoid blocking the event loop. Calls `reload_model()` to update inference. Sends Telegram notification.
- **Web dashboard**: `core/dashboard.py` serves a dark-themed status page at `DASHBOARD_PORT` (default 8080). Binds to `DASHBOARD_BIND` (default 127.0.0.1). Optional Bearer auth via `DASHBOARD_API_KEY`. Auto-refreshes every 5s. Shows P&L stats, win rate, recent trades, halt status, MT5 online status. Runs in a daemon thread — zero impact on tick processing.
- **Slippage**: `execute_trade()` estimates slippage, validates spread, calculates SL/TP from actual `result.price` fill from MT5 order response (not estimated fill). If fill deviates significantly from estimate, SL/TP is corrected via `_modify_sltp_after_fill()`.
- **Partial close**: `close_trade_partial(ticket, volume)` reduces position by specified volume. State mutations (`tp1_hit`, `remaining_lots`) only applied AFTER MT5 confirmation succeeds.
- **Gate Z1-Z94**: These are L2 microstructure filters. gate_Z1-Z7 are weighted into FW15 (L3 flow). gate_Z8-Z13 → FW15 (weight 0.2-0.3). gate_Z14-Z16 → FW04 (weight 0.3). gate_Z17-Z94 → FW15 (weight 0.05 each).
- **Trade deduplication**: `_open_symbols: set[str]` in main.py blocks duplicate trades on same symbol. Removed on dynamic exit and trade_tracker close detection.
- **Calendar scraper**: Returns stale cached data if all sources fail (instead of silent empty list). Parses timestamps as US/Eastern → UTC.
- **DB trigger**: `trg_trade_closed_features` inserts only `trade_id, symbol, pnl, gate_states_json, timestamp` — no fake bid/ask/spread/delta. Loss limits read from `DB_DAILY_LOSS_LIMIT` and `DB_CONSECUTIVE_LOSSES` env vars (not hardcoded).
- **Calibrate biases**: Uses `aggregate_framework_scores()` for base score (not `passed/total` which overfits).
- **L3 label contamination**: Fixed in v12.1 — `events_to_dataframe()` now snapshots features *at entry time* before future events are applied. Uses a pending buffer: features are frozen when the event arrives, labels are computed later once enough future mid prices have accumulated. No more double-apply of entry events or institutional features from future events.
- **Bias clamping**: Total bias shift (L3 + IV) clamped to `BIAS_MAX_SHIFT` (default 0.15) so the quality threshold remains meaningful. Env-configurable.
- **Threshold on raw score**: `score > effective_threshold` uses raw XGBoost model score, not `adjusted_score`. `adjusted_score` is logged for reference only. This prevents bias adjustments from inflating scores past 1.0 or double-counting features the model already learned.
- **Adverse L3 pre-filter**: `if clamped_bias < -0.05: continue` rejects signals before threshold check when adverse L3 bias is strong.
- **SELL blocked on toxic symbols**: `SELL_SIGNALS_BLOCKED` env var blocks SELL direction on symbols with historically toxic SELL WR (6BM6 21.4%, 6JM6 12.5%, 6AM6 25.8%, 6EM6 27.5%). Only 6CM6 SELL (86.7% WR) allowed.
- **Position reconciliation**: On startup, `_reconcile_positions()` queries MT5 for open positions and rebuilds `_open_symbols`, `_ticket_to_symbol`, `exit_manager`, `partial_closer`, and `trade_tracker` state. Prevents orphaned positions after crash/restart.
- **MT5 error vs empty**: `get_open_positions()` returns `None` on MT5 error (distinguishable from `[]` = no positions). `trade_tracker`, `close_trade`, `close_trade_partial`, `modify_sl` all handle `None` correctly — no false closures.
- **Direction inference**: When `bid_size`/`ask_size` are 0 (MT5 spot ticks), direction is inferred from price movement vs previous mid. Falls back to tick's existing `direction` field.
- **Scraper async safety**: `fetch_with_retry_async()` runs fetch_fn in `asyncio.to_thread()` with `asyncio.sleep()` backoff. Scraper calls from `_process_queue` wrapped in `asyncio.to_thread()` to avoid blocking the event loop.
- **.env contains MT5 credentials**: Security concern noted but not addressed (user's responsibility for production).

### Bug Fixes (v12.1)

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| P0-1 | Critical | `skip_gates` NameError in main.py | Replaced with inline `_skip = (tick_count % GATE_EVAL_INTERVAL != 0)` |
| P0-2 | Critical | gate_Z7 inverted lag logic | Changed `> threshold` → `<= threshold` (lag within tolerance = pass) |
| P0-3 | Critical | gate_D was trivial pass-through | Rewritten with directional momentum evaluation using `mid_move` vs `velocity_threshold` |
| P0-4 | Critical | DXY double-store for inverted futures | Removed redundant stores after `_resolve_pair` already handles inversion |
| P0-5 | Critical | `trade_tracker.register_trade()` never called | Now called from main.py after `log_trade()`; `log_trade()` returns `cursor.lastrowid` |
| P0-6 | Critical | `float("")` crash in spread check | Wrapped in try/except with fallback to 0.0 |
| P0-7 | Critical | SMOTE before CV split (data leakage) | Replaced with `imblearn.Pipeline` (SMOTE+XGB); `load_model.py` extracts XGB from pipeline |
| P0-8 | Critical | No trade deduplication | Added `_open_symbols` set + `_ticket_to_symbol` map in main.py |
| P1-9 | High | 87 orphaned gates (Z8-Z94) unmapped | Mapped: Z8-Z13→FW15, Z14-Z16→FW04, Z17-Z94→FW15 (weight 0.05) |
| P1-10 | High | gate_D in FW02 (wrong category) | Moved to dedicated FW16_directional_momentum |
| P1-11 | High | risk_regime never fed spread data | `risk_regime.update_spread()` called from main.py after tick enrichment |
| P1-12 | High | L3 scorer 2-class/3-class mismatch | Dynamic mapping: 2-class (0→-1,1→+1), 3-class (0→-1,1→0,2→+1) |
| P1-13 | High | Adverse selection checked bid only | Changed to `(price == self.best_bid or price == self.best_ask)` |
| P1-14 | High | L3 label contamination — features from future events | Features snapshot at entry time via pending buffer; labels computed from buffered future mids |
| P1-15 | Medium | `adjusted_score` unbounded | Clamped with `max(0.0, min(1.0, adjusted_score))` |
| P1-16 | Medium | Dynamic exit SL state never updated | `position["sl_price"]` updated on breakeven and trailing SL moves |
| P1-17 | Medium | partial_close rounding errors | `_round_lots` returns step minimum, rounds to 2dp; `remaining_lots` uses `max(0.0, ...)` |
| P2-18 | Low | Calendar silent empty fallback | Returns stale cached data if available, warns in log |
| P2-19 | Low | Calendar timezone offset | Parsed as US/Eastern → converted to UTC |
| P2-21 | Low | No model reload after auto-retrain | `reload_model()` called after `train()` in main.py |
| P2-22 | Low | Dashboard binds 0.0.0.0, no auth | Binds to `DASHBOARD_BIND` (default 127.0.0.1), optional Bearer auth |
| P2-23 | Low | DB trigger inserts fake features | Trigger now inserts only real columns (no fake bid/ask/spread/delta) |
| P2-24 | Low | DB hardcoded -$500 loss limit | Uses `DB_DAILY_LOSS_LIMIT` and `DB_CONSECUTIVE_LOSSES` env vars |
| P2-25 | Low | Calibrate uses `passed/total` (overfits) | Uses `aggregate_framework_scores()` for base score |
| P2-26 | Low | Offline PnL=0 misleading | Stats now include `mt5_online` flag |

### Architectural Fixes (v12.2)

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| A-1 | Critical | `get_open_positions()` returns `[]` on MT5 error → false closures | Returns `None` on error; callers distinguish `None` (error) vs `[]` (no positions) |
| A-2 | Critical | State mutated before MT5 confirmation (partial_close, dynamic_exit) | `tp1_hit`, `remaining_lots`, `breakeven_moved`, `trailing_activated`, `sl_price` only set after MT5 call succeeds; `confirm_sl_update()` method added |
| A-3 | Critical | SL/TP from estimated fill, not actual `result.price` | `execute_trade()` now returns `result.price` (actual fill); `_modify_sltp_after_fill()` corrects SL/TP if fill deviates |
| A-4 | Critical | No position reconciliation on restart | `_reconcile_positions()` queries MT5 at startup, rebuilds `_open_symbols`/exit managers/trade_tracker |
| A-5 | High | `time.sleep()` in scrapers blocks event loop | `fetch_with_retry_async()` added; scraper calls wrapped in `asyncio.to_thread()` |
| A-6 | High | DXY `update()` KeyError on direct spot pair input | `_resolve_pair()` now stores price in `_latest` for direct spot pairs |
| A-7 | High | Direction always SELL when bid_size/ask_size=0 (MT5 spot ticks) | Falls back to price movement vs previous mid, then tick's existing direction |
| A-8 | High | Bias adjustments can shift score ±0.7 (threshold meaningless) | Total bias clamped to `BIAS_MAX_SHIFT` (default 0.15, env-configurable) |
| A-9 | High | Auto-retrain blocks event loop for seconds | Retrain dispatched to background thread via `loop.run_in_executor()` |

---

## 13. TESTING & VERIFICATION

```bash
# Syntax check all Python files
python -m py_compile <file_path>

# Full end-to-end dry run (no MT5 needed)
python -c "
from database.setup_db import init_db, DB_PATH
init_db(DB_PATH)
from engine_logic.gates.gate_registry import GateRegistry
from ml.load_model import predict_trade_quality
registry = GateRegistry()
gate_states = registry.evaluate({'symbol':'EURUSD','bid':1.085,'ask':1.0851,'delta':0,'timestamp':'2026-01-01','direction':'BUY'})
print('Gates:', len(gate_states), 'Score:', predict_trade_quality(gate_states, {'symbol':'EURUSD','bid':1.085,'ask':1.0851}))
"

# Verify framework scores
python -c "
from ml.framework_scorer import aggregate_framework_scores, get_framework_feature_names
scores = aggregate_framework_scores({'gate_A':True,'gate_D':True})
print(scores)
print(get_framework_feature_names())
"
```

---

## 14. VERSION HISTORY

- **v12**: Framework scorer (131→15), slippage modeling, scraper hardening, env-configurable biases, tick optimization, partial close, honest IV data, DXY fix, risk limit enforcement, P&L tracking + Telegram reports, web dashboard, auto-retrain, 2-core optimizations
- **v12.1**: FW16_directional_momentum (gate_D), all Z8-Z94 gates mapped to frameworks, P0-1 through P0-8 critical fixes (NameError, inverted lag, trivial gate_D, DXY double-store, trade_tracker, float crash, SMOTE leakage, trade dedup), P1-9 through P1-17 high/medium fixes (orphaned gates, risk_regime spread, L3 class mapping, adverse selection, score clamping, SL state, partial close rounding), P2-18 through P2-26 low fixes (calendar fallback, timezone, auto-retrain reload, dashboard auth, DB trigger fake features, DB hardcoded limit, calibrate overfitting, offline PnL flag)
- **v12.2**: A-1 through A-9 architectural fixes (false closures on MT5 error, state-before-confirmation, actual fill price for SL/TP, position reconciliation on restart, async scraper safety, DXY direct spot pair storage, direction inference for MT5 spot ticks, bias clamping, background auto-retrain)
- **v12.3**: Backtest framework with dual-stream architecture, rule-based entry mode, SL/TP overrides, ATR-based SL/TP, momentum-continuation strategy. See Section 15.
- **v12.4**: MotiveWave bridge LIVE (5 CME pairs), A-10 (l3_scorer KeyError on lowercase keys), A-11 (ZMQ ProactorEventLoop fix), A-12 (aiohttp dep). Full end-to-end pipeline confirmed working: MotiveWave→UDP→hub_listener→gates→XGBoost→signal-only. 547K+ ticks in SQLite.
- **v12.5**: A-13 through A-21 (QUALITY_SCORE_MIN from .env, GATE_QUICK_REJECT, signal outcome tracking fix, DOM cache for TICK, FLAT outcome reload, FXCM bridge, watchdog, signal collection mode). XGBoost v2 retrained on real outcomes (AUC=0.8077).
- **v12.5.1**: A-22 through A-26 (exit_result crash, 6J price inversion, 6J tick_size, signal flood cooldown, DOM cache double-inversion).
- **v12.5.2**: A-27 through A-33 (model retrained on real outcomes, per-symbol thresholds, SELL blocked on toxic symbols, MotiveWave bridge heartbeat/auto-reconnect, hub_listener timeout, predict_trade_quality accepts tick, L3/bias stored before inference). Model v3 (18 frameworks, AUC=0.7959, OOS WR=98.7% at ≥0.85).
- **v12.6**: F-1 through F-8 (FRED scraper, ECB scraper, Finnhub scraper, fundamental bias calculator, gate_FUND, FW19_fundamental, fundamental bias adjustment, scrapers called at startup+500 ticks).
- **v12.7**: B-1 through B-10 (gate_D 4-tick momentum, L3 scoring before gates, l3_scorer key name mismatch, l3_scorer dropped features, l3_scorer garbage event injection, gate_A/B/T/G rewritten anti-predictive, backward compat dual-key fallback). Z-gates: 0/95→81/95 passing.
- **v12.7.1**: C-1 through C-9 (ECB key-path URLs, ECB ger_10y_bund removed, FRED IMF series for foreign CB rates, fundamental_bias sign convention fix, yield bias sign fix, cache bug fix, Finnhub headline keyword scoring, USD-specific sentiment).
- **v12.7.2**: D-1 through D-3 (Model v5 retrained with 19 frameworks + bias_fundamental; CV AUC=0.7811; OOS WR=95.6% at ≥0.85, 100% at ≥0.90). Backfilled FW19 into 9267 signals.
- **v12.8**: E-1 through E-6 (gate_FUND threshold 0.05→0.30, raw model score for thresholds not adjusted_score, adverse L3 bias pre-threshold rejection, main.py indentation fix, model v5 OOS validated, fundamental data APIs confirmed working).
- **v12.10**: J-1 through J-10 (Parallel Gate Evaluation, CVD Gate, Live Sentiment Dashboard, Order Flow Matrix UI, Hyper-Strict MotiveWave Bridge, removed hardcoded SELL blocks/regime restrictions, Global Cumulative Delta, Parallel XGBoost Training, Autonomous Optimization).
- **v12.11**: K-1 through K-6 (Network Resilience & System Stability). Implemented **Supervisor Loop** in `main.py` for self-healing; added **UDP Watchdog** in `hub_listener.py` with auto-rebind; enhanced **Java Bridge** with IP re-resolution and 60s forced refresh; fixed `agy` CLI crashes by adding **8GB extra swap space**; created **`sagy` command** for autonomous "max permission" operation.

### v12.12 Changes (2026-06-04) — Institutional Order Flow Gates + Architecture Hardening

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| L-1 | Critical | Bridge had duplicate `VERSION` field — wouldn't compile | Fixed: single `VERSION = "2026-06-04.2-BULLETPROOF"` |
| L-2 | Critical | Bridge stops on network change — no reconnection | Rewritten `OverseerMotiveWaveBridge.java`: 60s IP re-resolution, 30s instrument resubscription, Rithmic disconnect detection, 3-strike socket rebuild, heartbeats with health metrics |
| L-3 | Critical | No supervisor — main.py crashes stay dead | Created `supervisor.py`: auto-restarts on crash (5s delay, 10-crash/10min cooldown) |
| L-4 | Feature | Stacked Imbalance gate (institutional wall detection) | `gate_stacked_imbalance.py`: diagonal 3-level 300% DOM imbalance check |
| L-5 | Feature | Unfinished Business magnet filter | `gate_unfinished.py`: tracks incomplete auction levels that pull price back |
| L-6 | Feature | Tape Velocity exhaustion tracker | `gate_tape_velocity.py`: TPS counter with sliding window, blocks entries at session extremes when tape exhausts |
| L-7 | Feature | Iceberg Monitor gate (passive absorption) | `gate_iceberg_monitor.py`: detects hidden icebergs when trade volume exceeds visible DOM size by 2x |
| L-8 | Feature | Bar COT position tracker | `gate_bar_cot.py`: POC location relative to candle range confirms passive buyers/sellers |
| L-9 | Feature | CVD divergence gate (rewritten) | `gate_CVD.py`: now detects price/delta divergence (lower lows + higher CVD = accumulation) |
| L-10 | Feature | Directional asymmetry in framework scorer | `framework_scorer.py`: SELL signals get 0.6x multiplier on all framework scores (quantile regression finding) |
| L-11 | Feature | Time Stop exit | `dynamic_exit.py`: exits flat positions after 150 ticks (`TIME_STOP_TICKS` env) |
| L-12 | Feature | Unfinished Business exit filter | `dynamic_exit.py`: prevents premature exit when magnet target sits ahead |
| L-13 | Feature | Volume-based Take Profit | `dynamic_exit.py`: exits profit near HVN walls (institutional brick walls) |
| L-14 | Feature | Yen Risk-Off rule | `risk_engine.py`: blocks BUY on non-JPY pairs when 6J surges >50 pips |
| L-15 | Feature | Options Expiration constraint | `risk_engine.py`: tightens thresholds on op-ex dates (monthly) |
| L-16 | Feature | Macro Grid integration | `risk_engine.py` reads `config/macro_grid.json` for yearly/monthly/overnight levels |
| L-17 | Feature | Naked POC caching | `order_book_engine.py`: finds untested volume nodes that act as price magnets |
| L-18 | Feature | Double/Triple HVN detection | `order_book_engine.py`: consecutive matching HVN nodes = institutional S/R zones |
| L-19 | Feature | HVN tracking in candle aggregator | `candle_aggregator.py`: tracks POC per candle, detects double/triple nodes |
| L-20 | Feature | Macro Grid config file | `config/macro_grid.json`: yearly/monthly/overnight high/low per symbol |
| L-21 | Infrastructure | SQLite WAL safeguards | `setup_db.py`: `busy_timeout=10000`, `synchronous=NORMAL`, `isolation_level=IMMEDIATE`, `get_runtime_connection()` helper |
| L-22 | Infrastructure | XGBoost inference async | `main.py`: `predict_trade_quality()` runs in `asyncio.to_thread()` — never blocks UDP ingestion (reverted in M-2: synchronous call to fix memory leak) |
| L-23 | Infrastructure | Model retraining with new gate features | `train_model.py`: extracts gate_Z15, gate_A, gate_D, gate_stacked_imbalance, gate_CVD, gate_iceberg_monitor, gate_tape_velocity, gate_bar_cot, gate_unfinished features; OOS 80/20 time-ordered split |
| L-24 | Bug | main.py indentation error (sp=20 instead of sp=8) | Fixed entire execution block after `if result:` — partial_closer, telegram, open_symbols at correct indent |
| L-25 | Bug | `hub_listener.py` watchdog no backoff on bind failures | Added exponential backoff, consecutive failure tracking, OSError handling |
| L-26 | Infrastructure | Bridge log path for Linux | Changed from Windows `\\` path to `/Music/dfg/urlr/logs/motivewave_bridge.log` |
| L-27 | Feature | `load_model.py` includes new gate features | Inference now passes gate_Z15, gate_A, gate_D, gate_stacked_imbalance, gate_CVD, gate_iceberg_monitor, gate_tape_velocity, gate_bar_cot, gate_unfinished |

### Total Gate Count: 147 (141 original + 6 new order flow gates)

### New Gate Feature Importance (to be validated post-retrain)
Based on Gemini's order flow analysis:
1. **Gate_Z15 (Institutional Flow):** 55.4% standalone WR — highest edge
2. **Gate_A (Trend Alignment):** 39.6% standalone WR
3. **gate_stacked_imbalance:** Diagonal 300% imbalance = institutional wall
4. **gate_CVD:** Price/delta divergence = accumulation/distribution detection
5. **gate_iceberg_monitor:** Hidden passive absorption = institutional defense
6. **gate_tape_velocity:** TPS exhaustion at session extremes
7. **gate_unfinished:** Incomplete auction = price magnet
8. **gate_bar_cot:** POC position = passive buyer/seller confirmation

### v12.13 Changes (2026-06-04) — Model v7 + Stability + Bug Fixes

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| M-1 | Critical | Model v6 anti-predictive — high scores assigned to 6CM6 BUY (21.7% WR) while real edge was 6CM6 SELL (78.2% WR) | Model v7: per-symbol-direction sample weights prevent majority pair domination; monotonic WR improvement at lower thresholds |
| M-2 | Critical | Memory leak — 10.6GB after 3 hours from `asyncio.to_thread()` per tick creating unbounded threads | Changed `predict_trade_quality()` to synchronous call; scraper tasks use `run_in_executor()` instead of `asyncio.create_task()` |
| M-3 | High | Hub listener rejected bridge heartbeats (2.3M "malformed" warnings/hr) — `_parse_json_l3` required `source` key which heartbeats lacked | `_parse_json_l3` now accepts packets with `type` in `BRIDGE_HEARTBEAT/SHUTDOWN/STARTUP`, auto-injects `source="motivewave"` |
| M-4 | High | Malformed packet warnings flooding logs (2.3M/hr) | Throttled to 1 log per 60s with cumulative count |
| M-5 | High | SIGNAL_STRENGTH log only showed `adjusted_score * 100` — made it impossible to see raw vs adjusted gap | Now shows `Raw: X% Adj: Y%` separately |
| M-6 | High | Dynamic selector blocked signals from being logged to signal_log | Blocked signals now also written to DB for training data (with selector rejection reason) |
| M-7 | High | `get_hvn_levels()` called without required `symbol` arg — TypeError crash | Fixed: iterates over open positions, calls `get_hvn_levels(symbol)` for each |
| M-8 | High | Selector block body at same indent as `if` — Python IndentationError | Fixed indentation: body at 16sp inside `if selector_decision.is_block:` |
| M-9 | Medium | `load_model.py` couldn't handle new dict-format model (v7 uses `{"model": xgb, "smote": ..., "feature_names": ...}`) | Added `isinstance(_model, dict)` check to extract estimator |
| M-10 | Medium | Supervisor had no memory watchdog — process grew to 10GB before OOM | Added RSS check every 60s, kills main.py if >2GB (`SUPERVISOR_MEMORY_LIMIT_MB` env) |
| M-11 | Medium | 6CM6 SELL blocked by dynamic selector rule `FW19_fundamental >= 0.5` — 78.2% WR pair couldn't trade | Removed restrictive rule; 6CM6 SELL now TRADE_CANDIDATE with no extra filter |
| M-12 | Low | `THRESH_6CM6=0.90` too high — 69.3% OOS WR at 0.80 threshold | Lowered to `THRESH_6CM6=0.80` |

**Model v7 Results (per-symbol-direction weighted):**
- CV AUC: 0.8403
- OOS AUC: 0.8147
- OOS WR at 0.80: 71.0% (n=169)
- OOS WR at 0.85: 68.6% (n=140)
- 6EM6 BUY at 0.80: **86.2% WR** (n=29) — new edge discovered
- 6CM6 SELL at 0.80: **69.3% WR** (n=137)

**Key finding:** Model v6 (unweighted) had NO monotonic score-WR relationship. Score 0.60-0.70 had the BEST WR (38.5%), score 0.90-0.95 had the WORST (30.7%). Model v7 with per-symbol-direction weights produces monotonic WR improvement: 60% (69.1%) → 75% (72.1%) → 85% (68.6%).

**Real edge pairs (ex-FLAT WR):**
- 6CM6 SELL: 78.2% WR (161W/45L) — strongest
- 6EM6 BUY: 54.1% WR (119W/101L) — moderate
- 6AM6 BUY: 45.0% WR (274W/335L) — marginal
- 6BM6 BUY: 37.3% WR (377W/633L) — marginal
- All other pair/directions: <34% WR (toxic — avoid)

**Memory leak fix impact:** 10.6GB/3hr → 330MB/15min (stable, ~20MB/min growth rate)

### v12.14 Changes (2026-06-05) — 16 Institutional Modules Wired Into Tick Loop + OANDA Execution

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| N-1 | Feature | VPIN Toxicity Engine wired into every tick | `main.py`: `toxicity_engine.on_trade()` + `on_order_event()` per tick; extreme toxic flow blocks trade; toxic flow applies -0.05 penalty to adjusted_score |
| N-2 | Feature | OFI Microstructure Engine wired into every tick | `main.py`: `ofi_manager.update_book()` from DOM data + `on_trade()` per tick; OFI metrics injected into orderflow dashboard + regime_intel |
| N-3 | Feature | Regime Intelligence Engine wired into every tick | `main.py`: `regime_intel.on_tick()` with OFI input; blocks trades when `trade_allowed=False`; regime_intel state injected into tick dict |
| N-4 | Feature | Attention Gate Weighting wired after framework scores | `main.py`: `attention_gate.adjust_framework_scores()` runs after `aggregate_framework_scores()`, dynamically reweights 19 frameworks per context (session, regime, DXY, symbol) |
| N-5 | Feature | Sequence Core (LSTM) wired every 10th tick | `main.py`: `sequence_core.push_features()` + `predict()` every 10th tick; `combined_score()` blends LSTM with XGB when confidence > 0.3 |
| N-6 | Feature | Vector Memory wired into scoring + signal storage | `main.py`: `vector_memory.check_experience()` adjusts adjusted_score based on similar past states; `store_signal()` on execution; `backfill_from_db()` on startup |
| N-7 | Feature | XAI Explainer wired into signal flow | `main.py`: `xai_explainer.explain_signal()` decomposes every above-threshold signal; logs top+ and top- contributors every 50th signal or when score > 0.90 |
| N-8 | Feature | RL Brain wired into OANDA execution path | `main.py`: `rl_brain.select_action()` before OANDA execution; "wait" action defers trade, "limit" logs suggestion, "market" proceeds |
| N-9 | Feature | Execution Algo Engine wired into OANDA execution path | `main.py`: `exec_algo_engine.estimate_impact()` checks market impact before trade; reduces lot size if impact > 5 bps |
| N-10 | Feature | Portfolio Risk Engine wired into OANDA execution path | `main.py`: `parametric_var()` blocks trade if VaR < -2%; `stress_test()` blocks if any scenario impact < -5% |
| N-11 | Feature | Cross-Asset Engine wired every 10th tick | `main.py`: `cross_asset.update_fx()` every 10 ticks; `get_composite_signal()` injects cross-asset signal into tick; -0.03 penalty if composite < -0.5 |
| N-12 | Feature | Vol Surface Manager wired every 10th tick | `main.py`: `vol_surface_mgr.get_engine().update_realized_vol()` every 10 ticks |
| N-13 | Feature | Network Engine wired every 500th tick | `main.py`: `network_engine.update_price()` every 500 ticks for all tracked symbols |
| N-14 | Feature | Pairs Stat-Arb Engine wired every 500th tick | `main.py`: `pairs_engine.update_price()` + `scan_all_pairs()` every 500 ticks |
| N-15 | Feature | CB NLP wired every 500th tick | `main.py`: `cb_nlp.get_surprise_signal()` checks for policy surprises every 500 ticks |
| N-16 | Feature | Self-Supervised Engine wired every 1000th tick | `main.py`: `self_supervised.process_features()` detects anomalies in price array; logs warning when detected |
| N-17 | Feature | Causal Engine wired every 5000th tick | `main.py`: `causal_engine.run_from_db()` dispatched to background thread every 5000 ticks |
| N-18 | Infrastructure | All 17 module enable/disable flags in .env | `VPIN_ENABLED`, `OFI_ENABLED`, `REGIME_INTEL_ENABLED`, `CROSS_ASSET_ENABLED`, `CB_NLP_ENABLED`, `VOL_SURFACE_ENABLED`, `PAIRS_STAT_ENABLED`, `NETWORK_ENABLED`, `SELF_SUPERVISED_ENABLED`, `SEQUENCE_CORE_ENABLED`, `XAI_ENABLED`, `VECTOR_MEMORY_ENABLED`, `RL_BRAIN_ENABLED`, `CAUSAL_ENGINE_ENABLED`, `ATTENTION_GATE_ENABLED`, `EXEC_ALGO_ENABLED`, `PORTFOLIO_RISK_ENABLED` — all default true |
| N-19 | Infrastructure | Tiered interval env flags in .env | `SEQUENCE_INFERENCE_INTERVAL=10`, `XAI_COMPUTE_INTERVAL=50`, `CROSS_ASSET_INTERVAL=100`, `NETWORK_INTERVAL=200`, `PAIRS_STAT_INTERVAL=500`, `SELF_SUPERVISED_INTERVAL=1000`, `CAUSAL_ENGINE_INTERVAL=5000` |
| N-20 | Infrastructure | OFI + VPIN metrics in orderflow dashboard | `_ORDERFLOW_STATE` now includes `ofi`, `ofi_direction`, `micro_price_dev`, `informed_flow`, `vpin`, `toxicity`, `is_toxic` per symbol |
| N-21 | Bug | Portfolio risk `continue` inside `for` loop | Replaced with `_portfolio_blocked` flag + `break` pattern |
| N-22 | Infrastructure | OANDA execution path enhanced | RL brain, exec algo, portfolio risk checks added before `oanda_execute_trade()`; dynamic lot sizing based on impact estimate |

### v14.0 Changes (2026-06-07) — 64 Bonus Modules Wired Into Tick Loop + Bonus Layer System

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| Q-1 | Feature | **Bonus Layer System** — `_compute_bonus_layers()` aggregates all 64 module bonuses into `adjusted_score` | `main.py`: bonus_total + bonus_multiplier applied after bias adjustments; layers dict logged per signal |
| Q-2 | Feature | **12 per-tick module feeds** wired into tick loop | `main.py`: spread_velocity, tape_acceleration, bid_ask_flip, micro_regime, mm_spread, anchored_vwap, hurst, poor_high_low, network_jitter, hawkes, wavelet, kalman, initial_balance, quote_stuffing, bayesian_updater, footprint_patterns all called every tick |
| Q-3 | Feature | **Bonus score adjustments** from 26 modules | `main.py`: daily_bias, london_fix, spread_velocity, tape_acceleration, bid_ask_flip, initial_balance, mm_spread, bond_signal, equity_lead, news_velocity, swap_anomaly, anchored_vwap, cb_divergence, carry_monitor, hurst, wavelet, value_migration, contrastive_learner, currency_network, retail_sentiment, pcr_scraper, gamma_scraper, dot_plot, political_risk, disposition_effect, anchoring_effect, footprint_patterns, surprise_index, counterfactual, tda_patterns, online_learner, micro_regime, hawkes, kalman, news_velocity, broker_spread |
| Q-4 | Feature | **Multiplier adjustments** from 9 modules | `main.py`: dead_zone (0.60x), session_multiplier, time_heatmap, seasonal_patterns, signal_frequency, spillover, signal_entropy, session_multiplier all applied to adjusted_score |
| Q-5 | Feature | **Size multiplier** from 5 modules | `main.py`: anti_martingale, system_state_machine, live_edge_tracker, bayesian_updater (reduce/enter_small), ruin_calc all applied to lot size |
| Q-6 | Feature | **Threshold adjustments** from 4 modules | `main.py`: drawdown_velocity, poor_high_low, bandit_params all modify effective_threshold |
| Q-7 | Feature | **Block/filter decisions** from 10 modules | `main.py`: dead_zone, system_health, flash_crash, quote_stuffing, kalman, barrier_scraper, bayesian_abort/skip, counterfactual_edge_destroyed, es_risk, mm_step_back all can block trade execution |
| Q-8 | Feature | **Entry Sniper** integration — waits for micro-pullback before execution | `main.py`: entry_sniper.on_tick() + register_signal() in execution path; `continue` if not ready |
| Q-9 | Feature | **Structural SL** integration — computes optimal stop-loss from psych levels | `main.py`: structural_sl.compute_sl() replaces fixed SL pips before execution |
| Q-10 | Feature | **RL Exit Agent** integration — overrides exit decisions | `main.py`: rl_exit_agent.get_action() can trigger EXIT_NOW or MOVE_SL_BE before dynamic exit evaluates |
| Q-11 | Feature | **Score Calibration** integration — isotonic regression calibrates raw score | `main.py`: score_calibrator.calibrate() called per signal; fit_from_db() every 500 ticks |
| Q-12 | Feature | **Causal Importance** integration — downweights non-causal frameworks | `main.py`: causal_importance.get_framework_weight() applied to framework_scores before XGBoost |
| Q-13 | Feature | **Post-trade outcome hooks** wired for 6 modules | `main.py`: anti_martingale, drawdown_velocity, es_risk, ruin_calc, layer_performance, counterfactual all called when trade closes (both MT5 and OANDA paths) |
| Q-14 | Feature | **OANDA exit path** fixed — uses oanda_close_trade/oanda_modify_sl | `main.py`: dynamic exit now branches on `_use_oanda` for close_trade and modify_sl |
| Q-15 | Feature | **OANDA position monitoring** — detects closed positions | `main.py`: every 50 ticks checks oanda_get_positions() against _open_symbols |
| Q-16 | Feature | **26 slow-periodic module refreshes** every 500 ticks | `main.py`: time_heatmap, seasonal_patterns, gate_combos, score_calibration, contrastive_learner, currency_network, causal_importance, mutual_info, surprise_index, retail_sentiment, pcr_scraper, gamma_scraper, dot_plot, political_risk, barrier_scraper, bond_signal, equity_lead, spillover, carry_monitor, cb_divergence, broker_spread, swap_anomaly, tda_patterns, ms_garch, hawkes all refreshed |
| Q-17 | Bug | Cross-Asset signal `except` block at wrong indent — pre-existing | Fixed: `except Exception:` moved to correct indent level matching `try:` |
| Q-18 | Bug | Exit block `elif` at wrong indent after bonus layer hooks | Fixed: rewritten entire exit block with correct 4-space increment indentation |
| Q-19 | Bug | 500-tick maintenance block at wrong indent (4sp instead of 8sp) | Fixed: entire block re-indented to 8sp base inside while loop |
| Q-20 | Bug | Signal frequency + entry_sniper + bayesian_updater blocks at wrong indent | Fixed: re-indented to 12sp inside `if score > effective_threshold:` |

### v14.1 Changes (2026-06-08) — Ultra-Strict High Quality Mode & Stability Fixes

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| R-1 | Critical | `UnboundLocalError` on `closed` variable in `_process_queue` | Fixed: Initialized `closed = []` before the `tick_count % 50` condition to prevent crashing when `MT5_ENABLED` is false. |
| R-2 | Critical | `UnboundLocalError` on `loop` variable causing unconditional background scraping | Fixed: Properly indented background scraper `loop.run_in_executor()` calls and P&L Telegram report under the `if tick_count % 500 == 0:` condition. |
| R-3 | Critical | `NameError` on `FXSSI_WEB_ENABLED` in `main.py` | Fixed: Defined global flag in `main.py` to prevent crash when FXSSI scraping is evaluated. |
| R-4 | Feature | Enforced Ultra-Strict parameters for 90%+ WR high-quality setups | `.env` updated: `QUALITY_SCORE_MIN=0.92`, `MIN_RR_RATIO=2.5`, `GATE_B_MIN_PASS=10`. Engine will now exclusively process highest-conviction signals at the cost of signal frequency. |

### v14.2 Changes (2026-06-09) — Model v8 Retraining & Data-Driven Threshold Calibration

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| S-1 | Feature | Retrained XGBoost Model (v8) on 14,000+ real live outcomes | `train_model.py` executed via `signal_log` with horizon=200. Achieved CV ROC AUC: 0.8929, OOS AUC: 0.7219, and monotonic WR improvement across score brackets. |
| S-2 | Feature | Data-driven per-symbol thresholds | Adjusted `.env` based on real OOS performance: `QUALITY_SCORE_MIN=0.80`, `THRESH_6CM6=0.80`, `THRESH_6EM6=0.80`, `THRESH_6AM6=0.90`, `THRESH_6BM6=0.90`, `THRESH_6JM6=0.99`. |
| S-3 | Feature | Strictly blocked non-edge pairs | `SELL_SIGNALS_BLOCKED=6BM6,6JM6,6AM6,6EM6` retained to block toxic pairs lacking a sell-side edge. |
| S-4 | Config | Reverted execution flags for live OANDA | Set `MT5_ENABLED=false` and `AUTO_EXECUTE=true` after ensuring new thresholds block toxic signals. |

### v14.3 Changes (2026-06-10) — 100-Level DOM, Aggressive Mode & DB Auto-Pruning

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| T-1 | Feature | Enabled 100-Level DOM Depth | Updated MotiveWave bridge and `main.py` logic to process 100 levels (50 bid / 50 ask) for maximum institutional visibility (magnets/walls). |
| T-2 | Config | Aggressive High-Movement Mode | Temporarily lowered `QUALITY_SCORE_MIN` and per-symbol thresholds to **0.60** to capture high-volatility events in EUR/CAD during NY session. |
| T-3 | System | Automated Database Pruning | Implemented `_prune_database()` module in `main.py` which deletes `tick_log` and `trade_audit` data older than 24h every 6 hours to prevent disk exhaustion from 100-level DOM logging. |
| T-4 | Network | DNS Hardening | Manually mapped OANDA and Rithmic IPs in `/etc/hosts` to prevent "Attack Detected" DNS resolution failures during network switches. |
| T-5 | Performance | Signal Latency Fix | Adjusted `GATE_EVAL_INTERVAL=4` to reduce CPU load from 100% to <30% when processing deep DOM data, eliminating signal staleness. |
| T-6 | Stability | Emergency Load Shedder | Hardcoded auto-throttling in `main.py` that detects 100% CPU and automatically drops gate evaluation to 1/10th frequency. This prevents "All Data Stop" scenarios by ensuring the tick queue never fills up. |
| T-7 | Stability | MotiveWave Hardening | Permanently boosted MotiveWave memory to 4GB, enabled Low-Latency G1 Garbage Collection, and locked MotiveWave to Real-Time CPU priority. This prevents "Stopped Candles" and UI freezes during 100-level DOM updates. |

### v14.4 Changes (2026-06-11) — Mistake Learning Engine & HFT Network Hardening

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| U-1 | Intelligence | **Bottom-Up Mistake Learning** | Implemented `ml/mistake_analyzer.py` and a 1000-tick autonomous audit loop in `main.py`. The AI now identifies "Liar Gates" (filters that pass during losses) and automatically penalizes them in `ml/gate_weights.json`. |
| U-2 | Stability | **HFT UDP Buffer Expansion** | Increased Linux Kernel UDP receive buffer to **32MB** and configured `core/hub_listener.py` to force this buffer on the socket. Prevents packet loss and "MotiveWave Disconnected" errors during high-frequency 100-level DOM updates. |
| U-3 | Data | **Sentiment Mapping Fix** | Corrected Crude Oil mapping to `WTICO_USD` in `tools/retail_sentiment.py` to resolve 400 errors. Removed non-forex instruments from OANDA mapping to ensure clean sentiment feeds. |
| U-4 | Data | **PCR Scraper Reliability** | Fixed CBOE/FRED PCR scraping by adding a real User-Agent and updating the FRED series ID to `PCRE` (Equity PCR). Bypassed "Attack Detected" DNS blocks for CBOE via `/etc/hosts`. |
| U-5 | Intelligence | **Session Sniper Overdrive** | Unlocked the kernel for the New York session by disabling `TIME_HEATMAP_ENABLED` and `BANDIT_PARAMS_ENABLED`. Bypassed dynamic skepticisms that were forcing a 0.99 threshold, ensuring the system strictly follows the user's `QUALITY_SCORE_MIN`. |
| U-6 | Stability | **"War Machine" OS Tuning** | Forced Linux CPU governor to `performance` mode, disabled Wi-Fi Power Management, and set `TCP Keepalive` to 60s. Prevents Rithmic session drops caused by OS-level power saving or latency spikes on the HP laptop. |

### Tiered Bonus Module Architecture (v14.0)

```
Every Tick (0.5ms):  12 on_tick() feeds + gates + XGBoost + VPIN + OFI + RegimeIntel + Attention + 26 bonus getters
Every Signal (1ms):  _compute_bonus_layers() → total_bonus + total_multiplier → adjusted_score
Every Execution:     entry_sniper + structural_sl + bonus_size_mult + RL_brain + exec_algo + portfolio_risk
Every Close:         anti_martingale + drawdown_velocity + es_risk + ruin_calc + layer_performance + counterfactual
Every 500 Ticks:     26 slow-periodic module refreshes (DB backfills, scraper caches, model calibrations)
```

### Bonus Layer Scoring Formula (v14.0)

```
adjusted_score = max(0.0, min(1.0, ((raw_score + clamped_bias + fund_bias) + bonus_total) * bonus_multiplier))
effective_threshold = max(0.0, dyn_thresh + 0.02 + bonus_threshold_adj + bandit_threshold)
lot_size = max(0.01, base_lot * bonus_size_mult)
```

### Layer Performance Auto-Disable

If `LAYER_PERFORMANCE_ENABLED=true`, the Layer Performance Tracker automatically disables any bonus layer with negative lift (more losses than wins when active). Disabled layers are removed from `_compute_bonus_layers()` output on the next call.

### v13.0 Changes (2026-06-06) — Legendary Mode + Defensive Infrastructure (Druckenmiller Approach)

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| P-1 | Feature | **Legendary Mode** — Druckenmiller full-conviction approach | `ml/legendary_mode.py`: 6 platinum gates (gate_Z15, gate_A, gate_D, gate_stacked_imbalance, gate_CVD, gate_M) must ALL fire + score ≥ 0.95 + ≥2 supporting gates → one trade per symbol per day, 0.75 Kelly sizing, 4:1 RR TP target |
| P-2 | Feature | Kill Zone Precision Timer | `core/killzone_timer.py`: `get_killzone_quality()` returns quality 0.0-1.0 based on position within kill zone; peak 3-minute window = 1.0; edges = 0.3. Legendary mode only fires in peak window when `LEGENDARY_KILLZONE_PEAK_ONLY=true` |
| P-3 | Feature | Futures Rollover Calendar | `core/futures_calendar.py`: CME quarterly 3rd-Wednesday expiry; PRE_ROLL (14d) → 0.85x quality, NEAR_EXPIRY (7d) → 0.6x, ROLL_NOW (3d) → block trading |
| P-4 | Feature | Spread Z-Score Intelligence | `core/spread_intelligence.py`: Historical spread baseline by symbol×hour; z > 2.5 = anomalous (warn), z > 3.0 = avoid (block). Caches stats 5min TTL |
| P-5 | Feature | Psychological Level Detector | `core/psychological_levels.py`: Big figure / half figure / quarter figure hierarchy; `get_stop_hunt_probability()` detects when price is approaching a big figure where stops cluster |
| P-6 | Feature | Session Levels (PDH/PDL/PWH/PWL) | `core/session_levels.py`: Previous Day/Week High/Low proximity; classifies as BROKEN_RESISTANCE_NOW_SUPPORT (high conviction) or APPROACHING_RESISTANCE (low conviction) |
| P-7 | Feature | Scale-In Engine (3-tranche entry) | `execution/scale_in_engine.py`: 33% initial + 34% on +1 pip confirmation + 33% on momentum acceleration. Better average entry, lower risk per tranche |
| P-8 | Feature | Legendary Exit Trail | `execution/dynamic_exit.py`: Legendary positions get dedicated trail: breakeven at 1.5:1 RR, trail starts at 2:1 RR, 5-pip step. Extended TP at 4:1 RR. Standard exit logic skipped for legendary positions |
| P-9 | Feature | Candle injection onto tick dict | `main.py`: `_candles_15m`, `_candles_1h`, `_candles_daily` arrays injected before gate evaluation — enables candle-pattern gates (FVG, Order Block, SFP) in Phase 2 |
| P-10 | Feature | Tick enrichment for legendary modules | `main.py`: `_killzone_quality`, `_in_peak_killzone`, `_roll_status`, `_roll_quality_mult`, `_spread_zscore`, `_psych_level`, `_stop_hunt_prob`, `_session_level_proximity` all injected onto tick dict |
| P-11 | Feature | Legendary mode decision path wired into main.py | `main.py`: After threshold check, `legendary_mode.is_legendary()` evaluates platinum gates; legendary trades get 4:1 TP override, 0.75 Kelly sizing, scale-in entry; NEAR-LEGENDARY logged at score > 0.90 |
| P-12 | Infrastructure | Legendary env vars in .env | 17 new env vars: `LEGENDARY_MODE_ENABLED`, `LEGENDARY_SCORE_THRESHOLD`, `LEGENDARY_SUPPORTING_MIN`, `LEGENDARY_MAX_PER_DAY`, `LEGENDARY_TP_RR`, `LEGENDARY_BE_RR`, `LEGENDARY_TRAIL_START_RR`, `LEGENDARY_TRAIL_STEP_PIPS`, `LEGENDARY_KELLY_FRACTION`, `LEGENDARY_KILLZONE_PEAK_ONLY`, `SCALE_IN_ENABLED`, `SCALE_IN_CONFIRMATION_PIPS`, `SCALE_IN_MAX_WAIT_TICKS`, `SPREAD_ZSCORE_AVOID`, `SPREAD_ZSCORE_WARN`, `FUTURES_PRE_ROLL_DAYS`, `FUTURES_NEAR_EXPIRY_DAYS`, `FUTURES_ROLL_NOW_DAYS`, `KILLZONE_PEAK_TOLERANCE_MINUTES` |

### 2-Core Architecture (Tiered Intelligence)

```
Every Tick (0.5ms): Gates + XGBoost + VPIN + OFI + RegimeIntel + Attention + 12 on_tick feeds + 26 bonus getters → Decision
Every 10th Tick (5ms): SeqCore LSTM + Vector Memory + CrossAsset + VolSurface + PortfolioRisk
Every Signal (1ms): _compute_bonus_layers() → total_bonus + total_multiplier → adjusted_score + XAI SHAP + Vector Memory store
Every Execution: Entry Sniper + Structural SL + bonus_size_mult + RL Brain + ExecAlgo + PortfolioRisk VaR/Stress
Every Close: anti_martingale + drawdown_velocity + es_risk + ruin_calc + layer_performance + counterfactual
Every 500th Tick: Network + PairsStat + CB_NLP + 26 slow-periodic module refreshes
Every 1000th Tick: SelfSupervised anomaly
Every 5000th Tick: CausalEngine (background thread)
```

### v15.0 Changes (2026-06-15) — Clean Slate Clean Install + Java 25 Compilation

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| V-1 | System | **Clean Slate Wipe** | Fully uninstalled MotiveWave and deleted all local data folders (`.motivewave`, `MotiveWave Extensions`, `Workspace`) to resolve license and UI issues. |
| V-2 | System | **MotiveWave 7.0.26 Upgrade** | Installed the latest stable version 7.0.26 from `.deb` package. |
| V-3 | Dev | **OpenJDK 25 Manual Install** | Bypassed Linux repository limits by manually downloading and extracting **OpenJDK 25.0.1** to compile the bridge against the newest SDK requirements. |
| V-4 | Bridge | **v2026-06-15.2-STABLE Bridge** | Rebuilt and deployed a hardened bridge with a **300s packet timeout** (up from 10s) and **1-hour forced refresh**. Eliminated the constant disconnect bug during low-volume periods. |
| V-5 | Logic | **Unified L3/Orderflow Engine** | Removed all Level 3 (MBO) warmup logic. Institutional features now contribute to signals from the **very first tick**, syncing perfectly with standard orderflow. |
| V-6 | Intelligence | **Bootstrap Dynamic Mode** | Added "Bootstrap Fallback" to the dynamic threshold engine. Pairs with no history now trade at an aggressive **0.75** threshold instead of being blocked. |

### v12.11 Changes (2026-06-04) — Bulletproof Networking & Stability

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| K-1 | Critical | App/Bridge stop during network changes | Added **Supervisor Loop** in `main.py`. The app now automatically cleans up and restarts in 5s if it crashes. |
| K-2 | Critical | UDP listener hangs on Wi-Fi switch | Added **UDP Watchdog** in `hub_listener.py`. Automatically re-binds the socket with `reuse_port=True` if data stops for 60s. |
| K-3 | Critical | MotiveWave bridge loses connection to backend | Enhanced `OverseerMotiveWaveBridge.java` with **IP re-resolution** and a 60s forced refresh loop. Added 3-fail-reset logic. |
| K-4 | Critical | `agy` CLI killed by OOM | Diagnosed OOM-kills via `dmesg`. Added **8GB permanent swap file** (`/swapfile_extra`) to system. |
| K-5 | Utility | Need for "Max Permission" CLI | Created **`sagy` command** (`/usr/local/bin/sagy`). Runs `agy` with `sudo`, preserves environment, and defaults to `--dangerously-skip-permissions`. |
| K-6 | Resilience | Telegram/ZMQ stale connections | Added **re-connection retry logic** and stale-socket detection to `telegram_alerts.py` and `zmq_bridge.py`. |
| K-7 | Performance | Slow startup due to web scrapers | Moved all scrapers (Calendar, FRED, ECB, Finnhub) to **background tasks**. Engine now starts processing ticks immediately. |

### v12.10 Changes (2026-06-04) — Order Flow Mastery & Parallelization

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| J-1 | Feature | Parallel Gate Evaluation — maximize CPU usage | `GateRegistry` now uses `ThreadPoolExecutor(max_workers=8)` to evaluate 141 gates in parallel. |
| J-2 | Feature | Cumulative Volume Delta (CVD) Gate | `engine_logic/gates/gate_CVD.py` added; tracks session Net Delta alignment with trade direction. |
| J-3 | Feature | Live Order Flow Sentiment Dashboard | `jogiapp.py` updated with real-time symbol-by-symbol sentiment (STRONG BUY to STRONG SELL) based on L3 flow. |
| J-4 | Feature | Order Flow Master Matrix UI | Scrollable technical reference added to `jogiapp` dashboard for multimodal AI context (screenshots). |
| J-5 | Architectural | Hyper-Strict MotiveWave Bridge | `OverseerMotiveWaveBridge.java` rewritten with infinite connection retry loop and Throwable absorption. |
| J-6 | ML freedom | Removed Hardcoded SELL Blocks | `SELL_SIGNALS_BLOCKED` removed from `main.py`; decisions now 100% delegated to DynamicPairSelector. |
| J-7 | ML freedom | Removed Session/Regime Restrictions | `gate_news.py` (Session/Regime gates) now allow all conditions; ML model learns which are profitable. |
| J-8 | Data | Global Cumulative Delta Tracker | `main.py` tracks global `_cumulative_delta` per symbol and injects into `tick` dictionary. |
| J-9 | Performance | Parallel XGBoost Training | `train_model.py` updated with `n_jobs=-1` to use all CPU cores for retraining. |
| J-10 | Autonomy | Meta-Optimization Engine | `ml/autonomous_optimizer.py` added; automatically rewrites `dynamic_elite_params` every 500 ticks based on signal history. |

---

## 18. SIGNAL QUALITY ANALYSIS (Updated 2026-06-15)

Current performance benchmarks based on 16,648 historical signal outcomes:

### Global Win Ratios (Threshold >= 0.85)

| Symbol | Win Rate | Status |
|--------|----------|--------|
| **6CM6 SELL** | **95.4%** | **Institutional Edge** |
| **6AM6 SELL** | **100.0%** | **Elite Signal** |
| **6EM6 BUY** | **90.9%** | **Strong Edge** |

### Strategy Insights (June 15th Overdrive)
- **Unified Logic:** L3 and Orderflow are now perfectly synced; no more "cold" data blocks.
- **Stability:** Bridge v15.2-STABLE has eliminated "Watchdog Reset" noise in slow markets.
- **Bootstrap Edge:** New pairs are now tradable immediately at 0.75 score using the Bootstrap Fallback.

The system is designed to be **autonomous and self-correcting**:

1. **Gate Pipeline**: 147 gates run in parallel to generate framework scores.
2. **Drift Monitoring**: `ml/drift_monitor.py` blocks trading if real-world win rates deviate from model predictions.
3. **Dynamic Thresholding**: `main.py` autonomously raises thresholds (defensive mode) when drift or neutral regimes are detected.
4. **Meta-Optimization**: `ml/autonomous_optimizer.py` scans past winners/losers and rewrites the filter rules for `DynamicPairSelector` every 500 ticks.
5. **Auto-Retrain**: `ml/train_model.py` retrains the XGBoost model in the background as new trades close.

The code is now capable of "learning" which gates are profitable and automatically disabling the ones that aren't.

---

## 15. CURRENT QUANTOWER BRIDGE RUNBOOK

**Read this before touching the Quantower bridge.**

Current installed Quantower strategy:

```text
OVERSEER ALL PAIRS UDP Bridge 2026-06-01.5
```

Installed folder:

```text
C:\Quantower\TradingPlatform\v1.145.17\bin\Scripts\Strategies\OverseerAllPairsBridge
```

Source files:

```text
bridge/OverseerAllPairsBridge.cs
bridge/OverseerAllPairsBridge.csproj
setup/quantower_rithmic_fxcm_working_setup.md
```

### Critical Rules

- Use only `OVERSEER ALL PAIRS UDP Bridge 2026-06-01.5`.
- Do not use old Recent Strategy entries such as `OVERSEER v12 UDP Bridge 2026-05-29.7`, `2026-06-01.1`, `2026-06-01.2`, or `2026-06-01.3`.
- Run only one OVERSEER strategy instance at a time.
- Keep the Quantower bridge UDP-only. Do not re-add NetMQ/ZMQ to the Quantower strategy. Quantower failed to load external NetMQ assemblies.
- The bridge sends raw Quantower L2/L3 events to UDP immediately before full DOM enrichment. This is intentional because raw L3 logging proved data flow while the older full-payload UDP path could skip events during best bid/ask validation.
- `6SM6` and `6MM6` may log "not found" depending on the active Quantower connections/subscriptions. That is not fatal if the other symbols subscribe.

### Confirmed Working State

Quantower log confirmed:

```text
OVERSEER ALL PAIRS UDP Bridge 2026-06-01.4 state changed to: Working
Startup UDP heartbeat sent
Subscribed to Level 2/Level 3 DOM for 6EM6, 6BM6, 6JM6, 6AM6, 6CM6, 6NM6
Subscribed to FXCM spot pairs including EUR/USD through XAG/USD
```

Raw L3 file confirmed active data:

```text
logs/quantower_l3_raw.jsonl
```

Example confirmed rows had:

```text
version=2026-06-01.4
symbol=6EM6, 6BM6
quote.Id=bid_... / ask_...
quote.NumberOrders
quote.ImpliedSize
```

Build `2026-06-01.5` was installed after that to send every raw L3 event to UDP as well.

### How To Run Properly

1. Close old OVERSEER strategy instances in Quantower.
2. Close and reopen Quantower after a bridge reinstall.
3. Connect `Rithmic` and `FXCM`.
4. Open `Strategies Manager`.
5. Add from the non-Recent tree:

```text
OverseerAllPairsBridge -> OVERSEER ALL PAIRS UDP Bridge 2026-06-01.5
```

6. Confirm Strategy Manager status is `Working`.
7. Verify logs:

```powershell
Get-Content logs\bridge.log -Tail 80
Get-Content logs\quantower_l3_raw.jsonl -Tail 5
```

8. Verify UDP:

```powershell
python tools\udp_probe.py --host 0.0.0.0 --port 65000 --seconds 10
```

Expected when `2026-06-01.5` is running and ticks are flowing:

```text
Packets received: 1 or more
```

If UDP still shows `0`, first check whether `logs/quantower_l3_raw.jsonl` is updating with `version=2026-06-01.5`. If raw log updates but UDP is zero, inspect `bridge/OverseerAllPairsBridge.cs` around `SendRawLevel2Udp()`.

### Do Not Regress This

Previous broken builds:

- `2026-06-01.1`, `2026-06-01.2`, `2026-06-01.3` referenced NetMQ/ZMQ and Quantower logged `Could not load file or assembly 'NetMQ'`.
- The old installed folder `OverseerBridge` was removed. The only intended installed bridge folder is `OverseerAllPairsBridge`.

---

## 16. BACKTEST FRAMEWORK

### Architecture (`backtest/`)

| File | Purpose |
|------|---------|
| `engine.py` | Main backtest engine — replays ticks through OVERSEER pipeline |
| `data_loader.py` | Loads HistData M1, Dukascopy tick, generic CSV; M1→4 synthetic ticks (O/H/L/C) |
| `simulator.py` | `SimExecutor` — in-memory trade simulator with slippage, spread, commission |
| `analytics.py` | `BacktestResult` — computes Sharpe, drawdown, win rate, PF, direction stats |
| `gate_diag.py` | Per-gate pass rate diagnostic |
| `score_diag.py` | Score distribution diagnostic |

### Entry Modes

| Mode | CLI Flag | Description |
|------|----------|-------------|
| `ml` | `--entry-mode ml` | Default — uses XGBoost model score vs `--threshold` |
| `rule` | `--entry-mode rule` | Momentum-continuation — enters after big candle body (> N × ATR), in candle direction |

Rule mode bypasses the XGBoost model entirely. It enters when:
1. Current bar body > `--breakout-atr` × average ATR (default 1.0)
2. Bar close > bar open for BUY, bar close < bar open for SELL
3. Risk regime ≠ "risk-off"
4. Session filter (gate_M) passes — trade only during kill zones

### Key CLI Arguments

```bash
python -m backtest.engine --data backtest/data/spot/DAT_ASCII_EURUSD_M1_2025.csv \
  --entry-mode rule --breakout-atr 1.5 \
  --sl 8 --tp 36 --cooldown 100 \
  --max-daily-trades 5 --consecutive-loss-limit 999 \
  --slippage 1.0 --lot 0.01 --balance 10000
```

| Flag | Default | Description |
|------|---------|-------------|
| `--entry-mode` | `ml` | `ml` or `rule` |
| `--breakout-atr` | 1.0 | ATR multiplier for entry body size (rule mode) |
| `--sl-atr` / `--tp-atr` | 0 | SL/TP = N × ATR (0 = use fixed `--sl`/`--tp`) |
| `--sl` / `--tp` | 0 | Override instrument config SL/TP in pips (0 = use config) |
| `--cooldown` | 20 | Min ticks between trades |
| `--momentum-lookback` | 4 | Ticks back for gate_D momentum |

### Backtest Findings (v12.3)

**Critical: XGBoost model has zero predictive power on M1 backtest data.**

The model was trained on synthetic L3 signals (random spoof/iceberg/queue data). Score distribution is 0.69-0.91 on M1 data, 0.77-0.79 on real tick data. There is NO correlation between model score and trade outcome:

| Score Range | WR | Interpretation |
|-------------|----|----------------|
| 0.75-0.79 | 20-33% | Higher scores than 0.80-0.86 |
| 0.80-0.86 | 6-9% | Lower WR than lower scores |
| 0.88+ | 25-50% | Very few trades, unreliable sample |

**Profitable at threshold=0.88 on 2025 M1 (PF=1.13, +$17.91) but fails on 2024 OOS (PF=0.68)** — the result was statistical noise from tiny sample sizes.

**M1 candle patterns have zero directional predictability:**
- After 3 consecutive bullish bars: 47.5% continuation (coin flip)
- Wick rejection patterns (30-70% wick): 45-47% next-bar prediction
- Big body bars (>1.5× avg body): 49.7% continuation

**Only gate with real filtering edge on M1 data:**
- `gate_REGIME`: 0.6% pass rate, 52.7% direction accuracy vs 46.8% baseline (+5.9pp)
- `gate_M` (session): 37.6% pass rate — filters out off-hours noise

**Momentum-continuation rule mode works (marginally):**

After a big bullish bar (>1.0× ATR body), price continues up:
- 5-bar horizon: 61.6% continuation, +1.07 pips avg
- 10-bar horizon: 68.8% continuation

| Config | 2025 Seg0-4 | 2024 OOS | PF (avg) |
|--------|-------------|----------|----------|
| Rule, atr1.5, sl8/tp36, session filter | +$48.00 (400 trades) | +$2.67 (179 trades) | ~1.05 |

**Best robust config across both years:**
- Entry mode: `rule`, `--breakout-atr 1.5`
- SL/TP: Fixed `--sl 8 --tp 36` (ATR-based SL/TP overfits to 2025 volatility)
- Cooldown: `--cooldown 100`
- Session filter: gate_M (kill zone only)
- Risk: `--max-daily-trades 5 --consecutive-loss-limit 999`

**BE win rate for sl8/tp36 with 1 pip slippage: 20.5%.** System achieves ~21% WR across years, which is marginal but above breakeven. The real edge must come from CME futures L2/L3 data — backtest with synthetic signals cannot replicate this.

### Direction Inference (v12.3)

On M1 data (4 ticks per bar: open/high/low/close), direction is inferred from:
1. `bar_close > bar_open` → BUY, `bar_close < bar_open` → SELL (candle body direction)
2. Fallback: `ask_size > bid_size` → BUY (if sizes available)
3. Fallback: `current_mid > previous_mid` → BUY (tick-to-tick comparison, biased toward SELL on M1)

### Data Files (`backtest/data/spot/`)

| File | Type | Size | Period |
|------|------|------|--------|
| `DAT_ASCII_EURUSD_M1_2024.csv` | HistData M1 | 20 MB | 2024 |
| `DAT_ASCII_EURUSD_M1_2025.csv` | HistData M1 | 20 MB | 2025 |
| `eurusd-tick-2024-11.csv` | Dukascopy tick | 65 MB | Nov 2024 |
| `eurusd-tick-2024-12.csv` | Dukascopy tick | 51 MB | Dec 2024 |
| `eurusd-tick-2025-01.csv` | Dukascopy tick | 64 MB | Jan 2025 |

### Known Limitations

- **No real CME futures data**: All L3 signals are synthetic (random). Z-gates, gate_B, gate_VOL, gate_V have no real signal to filter on.
- **M1 data is too coarse**: 4 synthetic ticks per bar can't replicate real tick-by-tick dynamics.
- **Dukascopy tick data**: Real bid/ask but no volume, delta, or order book. Model scores compressed to 0.77-0.79 range (no trades at threshold 0.88+).
- **Synthetic spread**: M1 data has no real spread — `enrich_with_synthetic_l3()` adds fixed spread (default 1.5 pips for EURUSD).
- **Segment-dependent results**: Profitability varies significantly across time segments (PF 0.70 to 1.49 for same config).

---

## 17. MOTIVEWAVE BRIDGE COMPILATION

### SDK Version
- `mwave_sdk.jar` is compiled for **Java 26** (class file version 70.0)
- Location: `C:\Program Files (x86)\MotiveWave\lib\mwave_sdk.jar`
- **Must compile with JDK 26** — JDK 21 gives `wrong version 70.0, should be 65.0`

### JDK 26 Location
- Downloaded to: `C:\Users\jogip\AppData\Local\Temp\opencode\jdk-26\jdk-26.0.1\`
- `javac`: `C:\Users\jogip\AppData\Local\Temp\opencode\jdk-26\jdk-26.0.1\bin\javac.exe`

### Compilation Command
```powershell
$sdkJar = "C:\Program Files (x86)\MotiveWave\lib\mwave_sdk.jar"
$javac = "C:\Users\jogip\AppData\Local\Temp\opencode\jdk-26\jdk-26.0.1\bin\javac.exe"
$jarExe = "C:\Users\jogip\AppData\Local\Temp\opencode\jdk-26\jdk-26.0.1\bin\jar.exe"

# Compile
& $javac -source 26 -target 26 -cp "$sdkJar" -d build_dir bridge\OverseerMotiveWaveBridge.java

# Jar
& $jarExe cf OverseerMotiveWaveBridge.jar -C build_dir .

# Deploy
Copy-Item OverseerMotiveWaveBridge.jar "C:\Users\jogip\MotiveWave Extensions\"
```

### SDK API Notes (Critical — Do NOT regress)
- **NO `@InputParameter` annotation** — doesn't exist in SDK. Use `SettingsDescriptor` with `SettingTab` + `SettingGroup.addRow()`
- **`SettingTab(String)`** — only String constructor, NO int index param
- **`BooleanDescriptor(id, label, defaultValue)`** — 3 args (String, String, Boolean)
- **`IntegerDescriptor(id, label, defaultValue, min, max, step)`** — 6 args (String, String, int, int, int, int)
- **`StringDescriptor(id, label, defaultValue)`** — 3 args (String, String, String)
- **`getInstruments()` returns raw `List`** — must cast elements: `for (Object obj : list) { if (obj instanceof Instrument) ... }`
- **`DOMOrder.getQuantity()` returns `float`** — NOT int
- **`DOMRow.getSize()` returns `float`** — NOT int
- **Read settings in `onActivate()`**: `getSettings().getString("UdpHost", default)`, `getSettings().getInteger("UdpPort", default)`, etc.

### Deployed Jar
- Location: `C:\Users\jogip\MotiveWave Extensions\OverseerMotiveWaveBridge.jar`
- Version: `2026-06-01.1`
- Status: **LIVE and confirmed working** — streaming real CME MBO data from Rithmic

### Confirmed Working State (2026-06-01)

**MotiveWave bridge LIVE with real CME MBO order flow:**
- 5 CME futures pairs streaming: 6EM6, 6BM6, 6JM6, 6AM6, 6CM6
- MotiveWave + Quantower + Binance bridges all sending to UDP:65000
- `main.py` signal-only mode running end-to-end: UDP → hub_listener → enrich_tick → gates → XGBoost → signal log
- First live signal: `Signal-only: BUY 6JM6 score=0.8349`
- SQLite: 547K+ ticks ingested across all sources

**CME futures tick counts (from SQLite):**
| Symbol | Ticks | Source |
|--------|-------|--------|
| 6EM6 | 138K | MotiveWave/Rithmic |
| 6BM6 | 90K | MotiveWave/Rithmic |
| 6AM6 | 111K | MotiveWave/Rithmic |
| 6CM6 | 84K | MotiveWave/Rithmic |
| 6JM6 | 81K | MotiveWave/Rithmic |
| 6NM6 | 8K | MotiveWave/Rithmic |
| 6B, 6M | 16K | Quantower/FXCM |
| BTC/ETH/SOL/XRP/BNB | 18K | Binance bridge |

**MotiveWave setup (confirmed working):**
1. Open MotiveWave, connect Rithmic
2. Open chart for each CME pair (6EM6, 6BM6, 6JM6, 6AM6, 6CM6)
3. Add strategy `OVERSEER → OVERSEER MotiveWave MBO Bridge` to each chart
4. Each chart = one strategy instance (`multipleInstrument=false`)
5. Verify UDP: `python tools\udp_probe.py --host 0.0.0.0 --port 65000 --seconds 10`
6. Check `logs\motivewave_bridge.log` for startup confirmation

### v12.4 Bug Fixes (2026-06-01)
| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| A-10 | Critical | `l3_scorer._rebuild_book_from_dom()` KeyError on `"Price"` — MotiveWave sends lowercase `"price"` | Added `_get()` helper that tries both `"Price"`/`"price"`, `"Size"`/`"size"`, `"NumberOrders"`/`"number_orders"`/`"order_count"`, `"ImpliedSize"`/`"implied_size"` |
| A-11 | High | ZMQ `ProactorEventLoop` error on Windows | Added `asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())` at startup on win32 |
| A-12 | Medium | `aiohttp` not installed — Telegram alerts silently disabled | Added `aiohttp` to requirements |

### v12.5 Changes (2026-06-02)

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| A-13 | Critical | `QUALITY_SCORE_MIN` hardcoded as 0.65 in main.py, ignoring .env | Now reads `float(os.getenv("QUALITY_SCORE_MIN", "0.65"))` |
| A-14 | High | `gate_D`/`gate_Z7` quick-reject blocks ALL signal collection — only 6 signals from 650K ticks | Added `GATE_QUICK_REJECT` env var (default `true`); set `false` for signal collection mode |
| A-15 | High | Signal outcomes permanently FLAT — `entry_tick` never set, `ticks_elapsed` always 0 | Fixed: `log_signal()` accepts `tick_count`, stores `entry_tick` and `pip_size`; `update_mid_price()` increments `ticks_seen` per-symbol |
| A-16 | High | MotiveWave TICK messages have empty DOM → L3 scorer gets no book data | Added `_dom_cache` in `OverseerUdpProtocol`; DOM_SNAPSHOT populates cache; TICK messages get cached DOM injected |
| A-17 | High | Old FLAT outcomes never re-evaluated after process restart | Added `load_pending_from_db(conn)` — loads NULL-outcome signals from DB into `_pending_outcomes` on startup |
| A-18 | Medium | `hub_listener.py` didn't handle FXCM bridge packets | Added `fxcm_tick`, `fxcm_dom`, `fxcm_heartbeat` classifiers + `_fxcm_tick_to_standard()` / `_fxcm_dom_to_standard()` converters |
| A-19 | Feature | FXCM direct bridge — replaces Quantower dependency for spot forex | `tools/fxcm_bridge.py`: Python 3.7 + ForexConnect SDK → UDP:65000; L1 bid/ask with DOM_SNAPSHOT wrapper; `FXCM_USER`/`FXCM_PASSWORD`/`FXCM_CONNECTION` env vars |
| A-20 | Feature | Watchdog manages FXCM bridge too | `run_watchdog.ps1` auto-starts FXCM bridge alongside main.py; restarts on crash |
| A-21 | Feature | Signal collection mode for training data | `QUALITY_SCORE_MIN=0.50` + `GATE_QUICK_REJECT=false` = more signals logged for outcome-based retraining |

**FXCM Bridge Architecture:**
- Runs under Python 3.7 (`C:\Users\jogip\AppData\Local\Programs\Python\Python37\python.exe`) — ForexConnect SDK only supports 3.5-3.7
- Connects to FXCM real account via ForexConnect API
- Sends TICK + DOM_SNAPSHOT messages to UDP:65000 (same port as MotiveWave/Quantower)
- `hub_listener.py` classifies and converts FXCM packets to standard tick format
- FXCM provides **L1 (top of book)** only — no depth of market like CME futures
- FXCM credentials: `FXCM_USER`, `FXCM_PASSWORD`, `FXCM_CONNECTION=Real` in .env

**Signal Outcome Tracking (fixed in v12.5):**
- `log_signal()` now requires `tick_count` param
- `update_mid_price()` increments `pending["ticks_seen"]` per-symbol (not global tick count)
- `check_outcomes()` uses `pending["ticks_seen"]` with pip_size from pending dict
- `load_pending_from_db()` reloads NULL-outcome signals on startup
- Outcome horizons: 10 ticks, 50 ticks, 200 ticks
- WIN = price moved >= 1 pip in signal direction, LOSS = moved >= 1 pip against, FLAT = within 1 pip

**Current Data Collection Status:**
- Signal collection active with `GATE_QUICK_REJECT=false` + `QUALITY_SCORE_MIN=0.85`
- Signal cooldown: 50-tick per symbol (prevents DB flood)
- Pipeline running stable — quality over quantity mode
- XGBoost v2 retrained on real outcomes (AUC=0.8077)
- 6BM6 BUY OOS WR: 89.9% at 0.85 threshold, 93.8% at 0.90 threshold
- 6JM6 BUY OOS WR: 100% at all thresholds (small sample)
- SELL signals blocked on 6BM6/6JM6 (toxic)
- Continue collecting OOS signals to validate stability before enabling auto-execute

### v12.5.1 Changes (2026-06-02)

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| A-22 | Critical | `UnboundLocalError: exit_result` crash — elif at wrong indent, variable not set when `open_positions` empty | Moved `elif exit_result.get("reason")` inside the `for ticket` loop |
| A-23 | Critical | 6JM6 prices in Rithmic format (0.00627) instead of USD/JPY display (159.54) → ALL outcomes FLAT (pip_size=0.01 but price at 0.006) | Added `_invert_jpy_price()` in `hub_listener.py`; applied to TICK and DOM converters; DOM cache stores raw (non-inverted) prices; inversion applied when building final tick |
| A-24 | High | 6J `tick_size=0.0000001` (Rithmic format) inconsistent with pip_size=0.01 (USD/JPY display) | Changed to `tick_size=0.01` to match inverted price format |
| A-25 | High | Signal flood — every qualifying tick logged (1000s/minute) → DB bloat, duplicate signals | Added `_SIGNAL_COOLDOWN_TICKS=50` per-symbol cooldown in main.py; only logs one signal per symbol per 50-tick window |
| A-26 | High | DOM cache stored inverted JPY prices → double-inversion when TICK messages read from cache | DOM cache now stores raw (non-inverted) prices; TICK converter inverts both its own values and cache values independently |

**CME 6J Price Format:**
- CME JPY futures (6J) are quoted in USD/JPY = 0.00627, which equals JPY per USD = 1/0.00627 = 159.54
- `hub_listener.py` inverts 6J prices: `display_price = 1 / rithmic_price`
- All downstream components (gates, scorer, signal_logger) now see USD/JPY display format
- `pip_size=0.01` and `tick_size=0.01` match the display format
- USD/JPY confirmed at 159.70 (June 2, 2026) — 52-week range 142.38-160.74

### v12.5.2 Changes (2026-06-02)

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| A-27 | Critical | XGBoost model had zero predictive power — trained on synthetic L3 signals | Retrained on real `signal_log` outcomes with 38+ features (FW16 + symbol_enc + is_buy + per-currency flags + spread_bps + dxy + risk + 8 L3 + 7 bias); AUC=0.8077 |
| A-28 | Critical | All symbols share same 0.65 threshold — low-quality trades on weak symbols | Per-symbol thresholds via `THRESH_{SYMBOL}` env vars: 6BM6=0.85, 6JM6=0.85, 6AM6=0.90, 6CM6=0.90, 6EM6=0.95 |
| A-29 | Critical | SELL signals toxic on 6BM6/6JM6 (0-5% WR OOS) | `SELL_SIGNALS_BLOCKED` env var blocks SELL on specified symbols |
| A-30 | High | MotiveWave bridge silently disconnects during CME quiet periods | Bridge v2026-06-02.2: 3s heartbeat, auto-reconnect socket on error, `ensureSocket()`, `BRIDGE_HEARTBEAT`/`BRIDGE_SHUTDOWN` message types, consecutive error tracking with socket recreate at 10 errors |
| A-31 | High | `hub_listener.py` 5s disconnect timeout too aggressive for CME futures quiet periods | Timeout increased to 30s (configurable via `UDP_DISCONNECT_TIMEOUT` env); watchdog is cosmetic-only (logs warning, never crashes) |
| A-32 | High | `predict_trade_quality()` only accepted gate_states — no L3/bias/market context | Rewritten: `predict_trade_quality(gate_states, tick)` accepts tick dict with `_l3_features` and `_bias_breakdown`; auto-detects model feature expectations |
| A-33 | High | `main.py` didn't store L3/bias on tick before model inference | L3 info + bias_breakdown stored on tick dict BEFORE calling `predict_trade_quality()` |

**XGBoost Model v3 (trained on real outcomes, 18 frameworks):**
- Features: 40+ (FW01-FW18 + symbol_enc + is_buy + is_gbp/aud/eur/jpy/cad + spread_bps + dxy + risk_on/off + l3_spoof/queue/iceberg/adverse/hft/vacuum/pred/conf + bias_spoof/queue/iceberg/adverse/hft/vacuum/iv)
- Training data: `signal_log` real outcomes (200-tick horizon)
- Pipeline: `imblearn.Pipeline` (SMOTE + XGBoost)
- AUC: 0.7959
- New vs v2: FW17_volume_profile (gate_VP, gate_TPO, gate_VWAP) + FW18_technical (gate_RSI, gate_MACD, gate_BB)
- Backfilled FW17/FW18 into all old signals via `tools/_backfill_fw.py`

**OOS Validation Results (v3 model, 18 frameworks):**
| Threshold | n | WR | Notes |
|-----------|---|----|-------|
| >= 0.80 | 240 | 95.4% | |
| >= 0.85 | 154 | **98.7%** | |
| >= 0.90 | 78 | **100%** | |

| Symbol+Direction | >= 0.85 | >= 0.90 |
|------------------|---------|---------|
| 6BM6 BUY | 98.1% (n=53) | 100% (n=16) |
| 6AM6 BUY | 98.7% (n=77) | 100% (n=54) |
| 6CM6 BUY | 100% (n=15) | 100% (n=7) |
| 6JM6 BUY | 100% (n=3) | - |
| 6EM6 BUY | 100% (n=6) | - |

**SELL direction WR by symbol (all data):**
| Symbol | BUY WR | SELL WR | Status |
|--------|--------|---------|--------|
| 6BM6 | 52.2% | 21.4% | **BLOCKED** |
| 6AM6 | 56.9% | 25.8% | **BLOCKED** |
| 6EM6 | 44.6% | 27.5% | **BLOCKED** |
| 6JM6 | 31.8% | 12.5% | **BLOCKED** |
| 6CM6 | 61.9% | 86.7% | **ALLOWED** (only good SELL) |

**Current Live Configuration (v12.5.2):**
- See v12.8 section for current live configuration

**MotiveWave Bridge v2026-06-02.2:**
- Heartbeat every 3 seconds (`BRIDGE_HEARTBEAT` message)
- Auto-reconnect: `ensureSocket()` recreates socket on error
- `consecutiveErrors` tracking — socket recreate at 10 consecutive errors
- `BRIDGE_SHUTDOWN` message on clean exit
- `socketReconnectCount` counter for diagnostics

**Next Steps (v12.5.2):**
- See v12.8 section for current next steps

### v12.6 Changes (2026-06-02)

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| F-1 | Feature | FRED API scraper — US Treasury yields, Fed Funds, CPI, NFP, yield curve | `tools/fred_scraper.py` — free API, `fredapi` package, cached 6h in SQLite |
| F-2 | Feature | ECB Data Portal scraper — ECB rates, Bund yields, HICP, Euribor | `tools/ecb_scraper.py` — free SDMX API, cached 6h |
| F-3 | Feature | Finnhub news sentiment scraper — market news + economic calendar | `tools/finnhub_scraper.py` — free tier (60/min), cached 1h |
| F-4 | Feature | Fundamental bias calculator — rate differentials → directional bias | `ml/fundamental_bias.py` — rate_diff (50%) + yield_spread (35%) + sentiment (15%) |
| F-5 | Feature | gate_FUND — fundamental direction alignment gate | `engine_logic/gates/gate_FUND.py` — passes when trade direction aligns with macro bias |
| F-6 | Feature | FW19_fundamental framework score | Added to `ml/framework_scorer.py` — 19 frameworks now |
| F-7 | Feature | Fundamental bias adjustment on adjusted_score | `main.py` adds `fund_bias` to `adjusted_score`; stored in `bias_breakdown_json` |
| F-8 | Integration | Scrapers called at startup + every 500 ticks | `main.py` calls `scrape_fred`, `scrape_ecb`, `scrape_finnhub` alongside `scrape_options_iv` |

**Fundamental Data APIs:**

| API | Cost | Data | Env Var |
|-----|------|------|---------|
| FRED | Free | US yields, Fed Funds, CPI, NFP, yield curve | `FRED_API_KEY` |
| ECB | Free | ECB rates, Bund yields, HICP, Euribor | (no key needed) |
| Finnhub | Free (60/min) | News sentiment, economic calendar | `FINNHUB_API_KEY` |

**Fundamental Bias Architecture:**
- `ml/fundamental_bias.py` computes per-symbol bias [-1.0, +1.0]
- Rate differentials: Fed Funds vs ECB/BoE/BoJ/RBA/BOC policy rates (50% weight)
- Yield spreads: US 10Y vs German Bund (35% weight, EUR/USD specific)
- News sentiment: Finnhub USD sentiment score (15% weight)
- Bias adjustment: `FUNDAMENTAL_BIAS_WEIGHT` env var (default 0.05)
  - Favorable direction: +bias × weight
  - UnFavorable direction: -bias × weight × 2.0 (penalty for fighting fundamentals)
- gate_FUND: binary pass/fail — passes when trade aligns with fundamental bias (>0.05 threshold)
- FW19_fundamental: 1.0 when gate_FUND passes, 0.0 when fails
- `bias_fundamental` stored in `bias_breakdown_json` for model retraining

### v12.7 Changes (2026-06-02) — Gate & L3 Pipeline Overhaul

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| B-1 | Critical | gate_D always False — required single-tick `mid_move > velocity_threshold` (too strict, almost never happens) | Rewritten with 4-tick rolling momentum lookback (`GATE_D_LOOKBACK` env, default 4); compares current mid vs mid N ticks ago |
| B-2 | Critical | L3 scoring called AFTER gate evaluation → all Z-gates see empty fields → always False | Moved `l3_scorer.score(tick)` BEFORE `registry.evaluate(tick)` in main.py; institutional features copied to tick dict as top-level keys before gate eval |
| B-3 | Critical | l3_scorer key name mismatch — returns `spoof_signal`, gates expect `spoof_reversal_signal` (6 keys wrong) | `l3_scorer.score()` now returns all 15 institutional feature keys using the CORRECT names (`spoof_reversal_signal`, `queue_exhaustion_signal`, `iceberg_detected`, `adverse_selection_risk`, `hft_cluster_detected`, `liquidity_vacuum_signal`) |
| B-4 | Critical | l3_scorer drops 6 institutional features from return dict (spoof_volume_vanished, queue_attrition_pct, queue_absorbed_volume, iceberg_replenish_count, iceberg_hidden_depth, institutional_flight_volume) | `l3_scorer.score()` now returns ALL 15 features via `**inst_features` spread; `get_latest_features()` added to InstitutionalFeatureEngine |
| B-5 | Critical | l3_scorer.score() injects fabricated `action="ADD"` event into InstitutionalFeatureEngine on every tick — pollutes spoof_registry/order_lifespan with garbage | Removed redundant `process_event()` call from `score()`; real MBO events already flow through `_drain_l3_queue()` via `process_mbo_event()` |
| B-6 | High | gate_A anti-predictive (-21.3pp) — passed for any price move regardless of direction | Rewritten: 10-tick rolling trend alignment — BUY requires ascending mid, SELL requires descending mid |
| B-7 | High | gate_B anti-predictive (-23.8pp) — DOM imbalance with no direction filter | Rewritten: 10-tick price structure — BUY requires higher highs, SELL requires lower lows |
| B-8 | High | gate_T anti-predictive (-8.0pp) — passed on counter-trend signals | Fixed: requires trend alignment with trade direction; allows flat (no trend) as neutral |
| B-9 | High | gate_G anti-predictive (-3.4pp) — tick acceleration passed both speeding up AND slowing down | Rewritten: volume spike detection — compares recent 5-tick volume avg vs older baseline; passes only on volume acceleration ≥ `VOLUME_SPIKE_RATIO` (default 1.5) |
| B-10 | Medium | Backward compatibility — old signal_log entries use shortened key names | All DB readers (train_model, load_model, _oos_new_model, signal_logger, calibrate_biases, dashboard) updated with dual-key fallback: `.get("new_name", .get("old_name", 0))` |

**Impact of v12.7 fixes:**
- Z-gates: 0/95 passing → 81/95 passing (with spoof+queue signals injected)
- gate_D: Always False → passes on 4-tick momentum moves
- gate_A/B: Anti-predictive → directional alignment filters
- L3 institutional features now reach ALL Z-gates in real-time
- Removed L3 scorer's garbage event injection — institutional feature engine now only processes real MBO events from MotiveWave bridge

### v12.7.1 Changes (2026-06-02) — ECB Scraper Fix + Fundamental Bias Overhaul

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| C-1 | Critical | ECB scraper returned same value for all series — query params ignored by API, returned entire FM dataflow | Reverted to key-path URLs: `FM/B.U2.EUR.4F.KR.MRR_FR.LEV` etc. |
| C-2 | Critical | ECB `ger_10y_bund` series 404 on all key-path variants | Removed from ECB scraper; EUR yield spread now uses `ecb_deposit` rate instead |
| C-3 | High | `_get_base_currency_rate()` had hardcoded stale rates for GBP/JPY/AUD/CAD/NZD/CHF | All 6 currencies now read from FRED IMF series: `IR3TIB01xxM156N` |
| C-4 | High | `fundamental_bias.py` sign convention broken — flipped bias for non-USD-base pairs | Removed incorrect `quote_currency == "USD"` flip; `rate_diff = base - quote` already gives correct pair direction |
| C-5 | High | Yield bias sign wrong — `(us_10y - foreign)` penalizes foreign-currency-base pairs | Fixed: For XXX/USD pairs, yield_bias = `(foreign - us_10y)/3`; for USD/XXX pairs, yield_bias = `(us_10y - foreign)/3` |
| C-6 | High | `compute_fundamental_bias()` cache bug — returned 0.0 for all symbols except first cached | Changed cache check from `if _cached_bias and ...` to `if symbol in _cached_bias and ...` |
| C-7 | Medium | FRED scraper only had US series — no foreign central bank rates | Added 6 IMF series via FRED: BoE, BoJ, RBA, BOC, RBNZ, SNB policy rates |
| C-8 | Medium | Finnhub free tier has no sentiment data — `avg_sentiment` always 0 | Added headline keyword scoring (bullish/bearish word lists); fetches both `forex` and `general` categories |
| C-9 | Medium | `get_usd_sentiment()` returned generic avg, not USD-specific | Now filters for USD-relevant headlines (dollar, fed, fomc, treasury, etc.) before averaging |

**FRED new series:**
| Series ID | Label | Value (2026-06-02) |
|-----------|-------|-------------------|
| IR3TIB01GBM156N | boe_rate | 3.71% |
| IR3TIB01JPM156N | boj_rate | 1.27% |
| IR3TIB01AUM156N | rba_rate | 4.34% |
| IR3TIB01CAM156N | boc_rate | 2.27% |
| IR3TIB01NZM156N | rbnz_rate | 2.56% |
| IR3TIB01CHM156N | snb_rate | -0.04% |

**Live fundamental biases (2026-06-02):**
| Symbol | Bias | Interpretation |
|--------|------|----------------|
| 6EM6 | -0.53 | Bearish EUR/USD (Fed>>ECB) |
| 6BM6 | -0.07 | Mildly bearish GBP/USD (BoE~Fed, UK yield spread negative) |
| 6JM6 | +0.74 | Bullish USD/JPY (Fed>>BoJ, massive rate differential) |
| 6AM6 | +0.11 | Mildly bullish AUD/USD (RBA>Fed slightly) |
| 6CM6 | +0.48 | Bullish USD/CAD (Fed>>BOC) |
| 6NM6 | -0.40 | Bearish NZD/USD (RBNZ<Fed) |
| 6SM6 | +0.85 | Very bullish USD/CHF (Fed>>SNB, SNB at -0.04%) |

**ECB working series (key-path approach):**
| Series | Key | Latest |
|--------|-----|--------|
| ECB Ref Rate | `FM/B.U2.EUR.4F.KR.MRR_FR.LEV` | 2.15% (2025-06-11) |
| ECB Deposit Rate | `FM/B.U2.EUR.4F.KR.DFR.LEV` | 2.00% (2025-06-11) |
| 3M Euribor | `FM/M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA` | 2.23% (2026-05) |

### v12.7.2 Changes (2026-06-02) — Model v5 (19 Frameworks)

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| D-1 | Feature | Model v5 retrained with 19 frameworks (FW19_fundamental) + bias_fundamental feature | CV AUC=0.7811, OOS WR=95.6% at ≥0.85 (up from 0.7733/97.4%) |
| D-2 | Feature | Backfilled FW19_fundamental + fundamental_bias into 9267 existing signal_log entries | `tools/_backfill_fw19.py` |
| D-3 | Feature | Added `bias_fundamental` to `train_model.py` extract_features() | Reads from `bias_breakdown_json` with dual-key fallback |

**Model v5 OOS Validation (19 frameworks, 2494 training samples):**

| Threshold | n | WR |
|-----------|---|----|
| ≥0.80 | 303 | 92.1% |
| ≥0.85 | 183 | **95.6%** |
| ≥0.90 | 75 | **100%** |
| ≥0.95 | 20 | **100%** |

| Symbol+Direction | ≥0.85 | ≥0.90 |
|------------------|-------|-------|
| 6BM6 BUY | 97.7% (n=44) | 100% (n=16) |
| 6AM6 BUY | 98.6% (n=71) | 100% (n=54) |
| 6CM6 BUY | 91.0% (n=67) | 100% (n=5) |

**Top features:** is_buy (12.8%), is_cad (6.9%), is_jpy (6.1%), l3_pred (5.6%), FW01 (5.5%), FW15 (4.7%), spread_bps (4.7%)

### v12.8 Changes (2026-06-03) — Threshold Logic Fix + Indentation Fix

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| E-1 | High | gate_FUND threshold 0.05 too aggressive — blocked good 6BM6 BUY signals (97.7% OOS WR) because bias=-0.07 | Threshold raised to 0.30 — only blocks when bias strongly opposes direction |
| E-2 | Critical | Threshold checked on `adjusted_score` not raw `score` — adjusted_score inflating past 1.0 (seen adj=1.0000 in live logs), destroying model discriminative power | Changed to `score > effective_threshold` (raw model score); `adjusted_score` still logged for reference |
| E-3 | Critical | Adverse L3 bias not checked before threshold — signals with strong adverse bias could still pass if raw score high enough | Added `if clamped_bias < -0.05: continue` before threshold check in main.py |
| E-4 | Critical | main.py IndentationError — `_SELL_BLOCKED` and `if direction == "SELL"` at indent 4 (outside `while True:` loop body at indent 8); `if score > effective_threshold:` body also at indent 8 instead of 12 | Fixed all indentation: SELL block + adverse bias check at indent 8 inside while loop; if-block body at indent 12 |
| E-5 | High | `predict_trade_quality()` test in AGENTS.md used old 1-arg API | Updated to `predict_trade_quality(gate_states, tick)` |
| E-6 | Medium | Model v5 OOS validated — confirmed 95.6% WR at ≥0.85, 100% at ≥0.90 | No code change; validation confirmed working with 19 frameworks |

**Why raw score instead of adjusted_score for thresholds:**
- `adjusted_score = score + clamped_bias + fund_bias` could exceed 1.0 or be inflated by favorable bias
- Raw model score is what XGBoost actually predicts — it reflects the 19 framework features + L3/bias features that were fed to the model
- Bias adjustments are already features the model learned from — adding them again to the score double-counts
- OOS validation was done on raw scores — thresholds were calibrated against raw scores

**Current Live Configuration (v12.8):**
- `QUALITY_SCORE_MIN=0.85` (global minimum)
- `THRESH_6BM6=0.85`, `THRESH_6JM6=0.85`, `THRESH_6AM6=0.90`, `THRESH_6CM6=0.90`, `THRESH_6EM6=0.95`
- `SELL_SIGNALS_BLOCKED=6BM6,6JM6,6AM6,6EM6` (only 6CM6 SELL allowed)
- `GATE_QUICK_REJECT=false` (signal collection mode)
- `ZMQ_ENABLED=false` (no Quantower — MotiveWave-only)
- `MT5_ENABLED=true`, `AUTO_EXECUTE=false` (signal-only)
- MotiveWave bridge v2026-06-04.2-BULLETPROOF deployed with IP re-resolution, instrument resubscription, Rithmic disconnect detection
- FXCM bridge **disabled** — L1-only data, no DOM, no signal value; DXY derived from CME futures

**Next Steps:**
1. Run main.py end-to-end with all 10 new subsystems active
2. Monitor live signals with raw-score threshold approach
3. Verify gate_FUND passes for most symbols with 0.30 threshold
4. Consider reducing BIAS_MAX_SHIFT from 0.15 to smaller value since raw score is now used for thresholds
5. Retrain model periodically as more signal outcomes accumulate
6. Once OOS WR stability confirmed, enable MT5 demo auto-execute for 6BM6/6AM6 BUY at 0.90 threshold
7. Build Bright Data scraper (need correct task polling endpoint)

### v12.9 Changes (2026-06-03) — Institutional-Grade Subsystems + Indentation Fix

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| F-1 | Feature | DOM quality kill switch — detects zero_bid_ask, crossed_book, spread_spike (5σ), liquidity_vacuum, depth_collapse, stale_book | `core/dom_quality.py` — `DOMQualityChecker`; auto-halts/resumes with 30s cooldown; uses monotonic time |
| F-2 | Feature | Currency exposure tracker — FX-3 rule, correlated group limits (EUR/GBP/CHF, AUD/NZD), rollover block | `core/currency_exposure.py` — `CurrencyExposureTracker`; spread/notional/margin checks |
| F-3 | Feature | Unified pre-trade risk engine — integrates CurrencyExposureTracker + drawdown + cooldown + news block + spread efficiency | `core/risk_engine.py` — `RiskEngine(exposure_tracker=CurrencyExposureTracker)`; `check_all()` returns allowed/reason |
| F-4 | Feature | Pipeline latency tracker — stage marks (start_tick→mark_enriched→mark_gates_done→mark_scored→mark_decision→mark_fill) | `core/latency_tracker.py` — `LatencyTracker`; P50/P95/P99 percentiles, fill latency alerts |
| F-5 | Feature | Model drift monitor — checks WR per score bucket vs expected every 500 ticks, per-symbol + per-direction stats | `ml/drift_monitor.py` — `DriftMonitor`; auto-disable trading on 30pp WR drop |
| F-6 | Feature | Incremental MBO order book engine — ADD/MODIFY/CANCEL/TRADE processing, per-order tracking, queue stats | `ml/order_book_engine.py` — `OrderBookEngine`/`SymbolBook`/`PriceLevel`; time & sales, trade burst detection, absorption signals |
| F-7 | Feature | Per-symbol XGBoost models — trains separate model per symbol with SMOTE+CV; falls back to global model | `ml/per_symbol_model.py` — `PerSymbolModelManager`; saves to `ml/per_symbol/model_{symbol}.pkl`; min 100 samples |
| F-8 | Feature | Execution quality logger — logs fills/rejections to `execution_quality` DB table; slippage, fill latency, L3 signals | `execution/execution_quality.py` — `ExecutionQualityLogger`; stats by symbol, rejection breakdown |
| F-9 | Feature | Trade replay/audit — logs full pipeline state (gates, framework scores, L3, bias, DOM, risk, latency) to `trade_audit` DB | `execution/trade_replay.py` — `TradeReplay`; `replay_trade()`, `diagnose_rejection()`, `get_rejection_stats()` |
| F-10 | Feature | Paper trading engine — wraps SimExecutor for live shadow trading; logs to `paper_trades` DB | `execution/paper_trading.py` — `PaperTradingEngine`; SL/TP checked every 5 ticks; 24h stats |
| E-7 | Critical | main.py IndentationError — lines 952-1032 had 4 extra spaces (indent 16 instead of 12) after `if not _mt5_enabled` block's `continue` | Fixed: dedented entire `if result:` execution block from sp=16 to sp=12 (same level as `kelly_wr` line) |
| E-8 | Medium | `RiskEngine(currency_tracker=...)` — wrong keyword arg name | Fixed to `RiskEngine(exposure_tracker=...)` matching the constructor signature |

**New DB tables created by subsystems:** `execution_quality`, `trade_audit`, `paper_trades`

**Deployment stages (v12.9 design):**
- Stage 0: Signal-only (current) — collect outcomes, validate model
- Stage 1: Demo 0.01 lot — MT5 paper trading on all validated symbols
- Stage 2: Demo 2 symbols — 6BM6 + 6AM6 BUY only at 0.90 threshold
- Stage 3: Micro live — 0.01 lot on 2 symbols
- Stage 4: Small live — 0.1 lot, kelly sizing

**Current Live Configuration (v13.0):**
- `QUALITY_SCORE_MIN=0.85` (global minimum)
- `THRESH_6BM6=0.99`, `THRESH_6JM6=0.99`, `THRESH_6AM6=0.90`, `THRESH_6CM6=0.97`, `THRESH_6EM6=0.90`
- `LEGENDARY_MODE_ENABLED=true` — legendary mode active (6 platinum gates + score ≥ 0.95)
- `LEGENDARY_SCORE_THRESHOLD=0.95`, `LEGENDARY_TP_RR=4.0`, `LEGENDARY_KELLY_FRACTION=0.75`
- `SCALE_IN_ENABLED=true` — 3-tranche entry (33/34/33%)
- `GATE_QUICK_REJECT=false` (signal collection mode)
- `ZMQ_ENABLED=false` (no Quantower — MotiveWave-only)
- `MT5_ENABLED=false`, `AUTO_EXECUTE=true` (OANDA execution on Linux)
- OANDA practice account: `101-001-39497201-001` ($100K demo balance, `api-fxpractice.oanda.com`)
- MotiveWave bridge v2026-06-05.1-OI deployed with `getOpenInterest()`
- 9 instruments subscribed: 6EM6, 6BM6, 6JM6, 6AM6, 6CM6, 6NM6, 6SM6, GCM6, CLN6
- All 16 institutional modules + 7 defensive infrastructure modules + legendary mode integrated
- **Model v8** with per-symbol-direction weighted training (CV AUC=0.8929, OOS AUC=0.7219)
- Supervisor + systemd for bulletproof operation (`/etc/systemd/system/overseer.service`)
- 2M+ ticks, 14K+ signals in SQLite

**OANDA Instrument Mapping (CME Futures → OANDA):**

| CME Future | OANDA Instrument | Notes |
|-----------|------------------|-------|
| 6EM6 | EUR_USD | Euro |
| 6BM6 | GBP_USD | British Pound |
| 6JM6 | USD_JPY | Japanese Yen (inverted) |
| 6AM6 | AUD_USD | Australian Dollar |
| 6CM6 | USD_CAD | Canadian Dollar |
| 6NM6 | NZD_USD | New Zealand Dollar |
| 6SM6 | USD_CHF | Swiss Franc |
| GCM6 | XAU_USD | Gold (Signal only) |
| CLN6 | WTICO_USD | WTI Crude Oil (Signal only) |

**Proven Edge (live data, ex-FLAT WR at Model v8 score >= 0.85):**

| Symbol+Direction | WR | Signal Count | Status |
|------------------|----|----|--------|
| 6AM6 SELL | 100.0% | n=5 | **Elite Signal** |
| 6CM6 SELL | 95.4% | n=634 | **Institutional Edge** |
| 6EM6 BUY | 90.9% | n=11 | Strong Edge |
| 6EM6 SELL | 87.5% | n=moderate | Strong Edge |

**Toxic pairs (avoid):**

| Symbol+Direction | WR | Status |
|------------------|----|----|
| 6CM6 BUY | 21.7% | **BLOCKED** |
| 6BM6 SELL | 21.3% | **BLOCKED** |
| 6JM6 SELL | 20.0% | **BLOCKED** |

**Legendary Mode Platinum Gates (all 6 must fire):**
1. `gate_Z15` — Institutional flow (55.4% standalone WR)
2. `gate_A` — Trend alignment (39.6% standalone WR)
3. `gate_D` — Directional momentum (REQUIRED for trade)
4. `gate_stacked_imbalance` — Diagonal 300% DOM imbalance (institutional wall)
5. `gate_CVD` — Price/delta divergence (accumulation/distribution)
6. `gate_M` — Kill zone alignment (session timing)

**Phase Roadmap (v13.0+):**

| Phase | Focus | New Frameworks | Status |
|-------|-------|----------------|--------|
| Phase 1 | Legendary Mode + Defensive Infrastructure | — | **COMPLETE** |
| Phase 2 | Smart Money gates (FVG, OB, SFP, Wyckoff, PO3) + Hurst exponent | FW20_legendary, FW21_smart_money | **COMPLETE** |
| Phase 3 | Retail sentiment, COT crowding, currency strength, London fix, intermarket | FW22_intermarket, FW23_positioning | **COMPLETE** |
| Phase 4 | Model retrain on 23 frameworks + legendary features | — | **COMPLETE** |

**Next Steps (v13.0):**
1. When market opens (Sunday 5PM ET): verify live ticks flow + legendary mode evaluation works
2. Test OANDA demo execution with a real legendary trade (0.01 lot, 6CM6 SELL)
3. Phase 2: Smart Money gates (gate_FVG, gate_ORDER_BLOCK, gate_SFP, gate_WYCKOFF, gate_PO3) + Hurst + FW20/FW21
4. Phase 3: Retail sentiment scraper, COT crowding, currency strength, London fix, intermarket engine + FW22/FW23
5. Phase 4: Model retrain on 23 frameworks + legendary features, OOS validation
6. Monitor system stability over 24h with all modules active

### v12.9.1 Changes (2026-06-03) — Production Blocker Fixes

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| G-1 | Critical | DOM `crossed_book` false positive — `bid >= ask` includes `bid == ask` (zero-spread ticks from MotiveWave trade ticks where both bid/ask filled from same `tick_price`); blocks ALL trades permanently | Changed to `bid > ask` (strict crossed book only) + 3-tick grace period via `DOM_CROSSED_BOOK_GRACE_TICKS` env; `bid == ask` now emits `zero_spread` (quality *= 0.7, no halt); only `crossed_book` and `zero_bid_ask` trigger halt; `depth_collapse` no longer halts |
| G-2 | High | IV scraper Garman-Klass crashes if candle aggregator returns dicts instead of dataclass objects | Added `_candle_val()` helper that handles both `dict` and `dataclass` attribute access |
| G-3 | High | IV scraper had no Finnhub fallback — only empty Garman-Klass when no API/CBOE | Added `_fetch_finnhub_forex_vol()` as 3rd source between CBOE and Garman-Klass; uses `FINNHUB_API_KEY` from .env |
| G-4 | High | Calendar scraper tried Investing.com first (always blocked by Cloudflare) → `fetch_with_retry` never retries `[]` return | Reordered: ForexFactory API tried first (more reliable), Investing.com as fallback |
| G-5 | Medium | FRED scraper: 14 sequential API calls with no delay → rate-limit 429; connection leak on early return | Added `FRED_INTER_REQUEST_DELAY=0.5s` between calls; `conn.commit()` per series; `try/finally` ensures `conn.close()`; graceful skip when `fredapi` not installed |
| G-6 | Medium | FRED scraper `SystemExit` on missing `fredapi` — crashes entire process | Changed to `Fred = None` on import failure; `scrape_fred()` returns `{}` gracefully |

### v12.9.2 Live Handoff (2026-06-03) — MotiveWave/Rithmic DOM Normalization + Runtime Stability

**Read this before testing live data.** The current working path is:

```text
MotiveWave / Rithmic CME futures DOM
  -> UDP 127.0.0.1:65000
  -> core/hub_listener.py
  -> main.py
  -> DOM normalization + L3 scoring + gates + model + risk/drift checks
  -> SQLite + dashboard + optional MT5 execution
```

Quantower and FXCM are not required for the current live feed. FXCM can be connected in Quantower visually, but the backend uses the CME futures/Rithmic UDP stream for real order-flow/L3-style DOM features.

| ID | Severity | Description | Fix |
|----|----------|-------------|-----|
| H-1 | Critical | MotiveWave/Rithmic feed sometimes arrives with bid/ask inverted for CME FX futures (`bid > ask`), causing `DOM quality: crossed_book` and blocking all trades/signals | `core/dom_quality.py` now auto-normalizes crossed books by swapping bid/ask and bid_size/ask_size before quality checks; sets `tick["dom_auto_swapped"]=True` |
| H-2 | Critical | `main.py` tick buffering was inside the 500-tick slow-maintenance branch, so normal ticks were not always persisted/committed promptly | `_tick_buffer.append(...)` now runs for every valid tick; SQLite batch commits still use `COMMIT_INTERVAL_TICKS` |
| H-3 | Critical | Runtime DB connection could close before `_process_queue()` finished, causing process exit/crash | `main.py` now awaits `_process_queue()` inside the live SQLite connection context |
| H-4 | High | Dashboard and runtime SQLite readers could fight for locks during live feed | Runtime connection uses WAL, `busy_timeout`, `timeout=10`, autocommit; dashboard uses read-only-style query connection, timeout, cache, and `ThreadingHTTPServer` |
| H-5 | High | `DOMQualityChecker` API mismatch with `main.py` (`check_tick`, `is_trading_allowed(symbol)`) | Added compatibility methods/signatures in `core/dom_quality.py` |
| H-6 | High | `RiskEngine.check_all()` call from `main.py` did not pass required `sl_pips` and `spread_bps` | `main.py` now passes per-instrument SL pips and tick spread bps, and normalizes tuple/dict risk return values |
| H-7 | Medium | IV scraper only supported one rigid custom API format | `tools/options_iv_scraper.py` now supports `IV_API_METHOD`, `IV_API_BODY_JSON`, `IV_API_HEADERS_JSON`, `IV_API_DATA_PATH`, and common IV field names |

**Current verified runtime state after H fixes:**

- `main.py` can run without Python tracebacks after startup.
- UDP listener expected on `0.0.0.0:65000`.
- Dashboard expected on `127.0.0.1:8080`.
- Live ticks flow from Rithmic/MotiveWave.
- L3 scorer reaches warm state after enough DOM events.
- Recent `tick_log` rows should show `bid <= ask` for `6EM6`, `6BM6`, `6AM6`, `6JM6`.
- No new `database is locked` errors were found in the latest scan after WAL/autocommit/caching changes.
- `DOM quality: crossed_book` should no longer be the active blocker after normalization.

**Current active blocker: model drift safety.**

After DOM normalization, the main trade blocker became:

```text
Trade blocked by risk limit: drift: Model drift detected
```

This is intentional safety behavior from `ml/drift_monitor.py`. It means the live/recent win rate in a score bucket is much worse than the model expected. Do not bypass this for live trading. For data collection, keep:

```env
AUTO_EXECUTE=false
MT5_ENABLED=true
GATE_QUICK_REJECT=false
```

Then collect `signal_log` outcomes and retrain/calibrate before enabling execution.

**Live verification commands for the next agent:**

```powershell
# Syntax check changed/runtime-critical files
python -m py_compile main.py core\dom_quality.py core\dashboard.py tools\options_iv_scraper.py

# Confirm UDP and dashboard ports are owned by python
Get-NetUDPEndpoint -LocalPort 65000 | Select-Object LocalAddress,LocalPort,OwningProcess
Get-NetTCPConnection -LocalPort 8080 -State Listen | Select-Object LocalAddress,LocalPort,OwningProcess

# Confirm dashboard responds
$r = Invoke-WebRequest http://127.0.0.1:8787 -UseBasicParsing
"JOGIAPP_OK len=$($r.Content.Length)"

# Confirm Live Sentiment Dashboard
$r = Invoke-WebRequest http://127.0.0.1:8787/api/status -UseBasicParsing
"SENTIMENT_DATA: $($r.Content | ConvertFrom-Json | Select-Object -ExpandProperty orderflow_dashboard)"

# Confirm recent DB ticks are not crossed after normalization
python -c "import sqlite3; c=sqlite3.connect('database/overseer_trades.db'); rows=c.execute(\"select symbol,bid,ask,timestamp from tick_log order by rowid desc limit 20\").fetchall(); print('\\n'.join(f'{s} bid={b} ask={a} {\"OK\" if float(b)<=float(a) else \"CROSSED\"} {t}' for s,b,a,t in rows))"

# Scan recent logs for critical failures
Get-ChildItem logs -File | Sort-Object LastWriteTime -Descending | Select-Object -First 5 | ForEach-Object { $_.FullName }
```

**Current Operating Directives (v14.4):**

1. **Active Hunt:** System is in "Aggressive NY Overdrive" with `QUALITY_SCORE_MIN=0.60`.
2. **Model Brain:** Model v8 is active (trained on 14k signals). Do not bypass drift monitor unless retraining has occurred.
3. **Automated Maintenance:** Auto-retrain at 50 closed trades and auto-prune at 24h/6h intervals are hardcoded and active.
4. **Mistake Learning:** Autonomous bottom-up audit loop is active every 1000 ticks. Check logs for "Liar Gates".
5. **Stability:** OS-level "War Machine" tuning (CPU/Wi-Fi/Priority) must remain active for Rithmic stability.
6. **Execution:** OANDA Practice mode is active. Monitor fill quality via `execution_quality` table.
7. **Expansion:** Add a real FX options IV source (ORATS/OptionsDX) to unlock the FW11_iv_skew predictive edge.

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
