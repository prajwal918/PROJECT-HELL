# OVERSEER Forex Edition

Toxic Flow Arbitrage Engine for MT4/MT5

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure .env
cp .env.example .env
# Edit .env with your credentials

# 3. Run the hub
python hub.py
```

## Architecture

```
┌─────────────────┐     ZMQ      ┌─────────────────┐     API     ┌──────────┐
│  C# Scanner     │ ──────────▶  │  Python Hub     │ ─────────▶ │ Telegram │
│  (Quantower)    │    JSON      │  (Gate Engine)  │            │  Alerts  │
└─────────────────┘              └─────────────────┘             └──────────┘
                                        │
                                        │ MT5 API
                                        ▼
                                 ┌──────────────┐
                                 │   MT4/MT5    │
                                 │   Broker     │
                                 └──────────────┘
```

## Gate System (94 Total Edges)

### Core Gates (Blocking)

| Gate | Name | Description |
|------|------|-------------|
| I | Circuit Breaker | Halts after 2+ consecutive losses |
| C | Quality Score | Min 0.65 quality required |
| D | Daily Cap | Max 3 trades per day |
| J | Session Window | London/NY hours only (with KZ exceptions) |
| K | Volatility | ATR(14) >= asset minimum |
| E | HTF Alignment | 5-min + 15-min EMA aligned |
| F | Spread Monitor | Live spread <= max threshold |
| H | Tick Momentum | Tick confirmation in signal direction |
| U | DXY Correlation | USD Index alignment |
| Z3 | PD Zone | Premium/Discount zone check |

### Forex-Specific Gates

| Gate | Name | Description |
|------|------|-------------|
| FX-1 | RR Filter | Min 1:1.5 reward:risk ratio |
| FX-2 | Spread Efficiency | Spread < 20% of SL distance |
| FX-3 | Correlation Limit | Max ±2 exposure per currency |
| FX-4 | Rollover Block | No entries 20:55-21:05 UTC |
| FX-10 | Carry Bias | +0.03 bonus for carry-favorable direction |

### Bonus Gates

| Gate | Name | Bonus |
|------|------|-------|
| G | Round Numbers | +0.03 |
| Z6 | Kill Zone | +0.06 |
| Z7 | OTC Lag | +0.10 |
| Z4 | FVG Stack | +0.08 |
| N | Liquidity Pool | +0.08 |

## Signal Flow

```
1. C# Scanner detects Phase 1 candle pattern
2. Gate A (levels) evaluated
3. Gate B (order flow) evaluated - min 6/17
4. Gate K (ATR) check
5. Signal sent via ZMQ to Python Hub
6. Python Hub evaluates remaining gates
7. If passed → Telegram alert + journal log
8. If AUTO_EXECUTE=true → MT5 order placed
```

## Configuration (.env)

```bash
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# MT5
MT5_ACCOUNT=12345678
MT5_PASSWORD=your_password
MT5_SERVER=ICMarkets-Demo
AUTO_EXECUTE=false

# Risk
RISK_PER_TRADE_PCT=1.0
MAX_DAILY_LOSS_PCT=3.0
MAX_WEEKLY_LOSS_PCT=6.0
MAX_DAILY_TRADES=3

# Gate Thresholds
QUALITY_SCORE_MIN=0.65
GATE_B_MIN_PASS=6
MIN_RR_RATIO=1.5

# ZMQ
ZMQ_PORT=5555
```

## Trade Management

### Position Sizing
- Risk-based: `lots = (balance × risk%) / (SL_pips × pip_value)`
- Default: 1% per trade
- Auto-adjusts for currency pair

### Stop Loss
- Placed at candle wick extreme + buffer
- For UP: SL = wick_low - spread - 1pip
- For DOWN: SL = wick_high + spread + 1pip

### Take Profit
- TP1: 1R (50% position close)
- TP2: 2.5R (remaining position close)
- SL moved to BE after TP1 hit

## Journal Analytics

```bash
# Run analytics
python -c "from hub.journal import print_analytics; print_analytics()"
```

Output:
```
Overall : 45/60 (75.0%) PnL: +$234.50

-- By Gate B Score --
Gate B 14/17: 8 trades, 87.5% WR, +$156.00
Gate B 11/17: 12 trades, 75.0% WR, +$98.00
...
```

## Session Schedule (UTC)

| Session | Start | End |
|---------|-------|-----|
| London | 07:00 | 16:00 |
| NY | 12:00 | 21:00 |
| Overlap | 12:00 | 16:00 |
| Asian | 00:00 | 08:00 |

### Kill Zones
| Zone | Start | End |
|------|-------|-----|
| London Prime | 03:00 | 04:00 |
| NY Open | 09:30 | 10:30 |
| London Close | 11:00 | 12:00 |
| Asian | 20:00 | 21:00 |

## Risk Management

1. **Daily Cap**: Max 3 trades per day
2. **Circuit Breaker**: Halts after 2 consecutive losses
3. **Weekly Cap**: Max 6% weekly loss
4. **Correlation**: Max ±2 exposure per currency
5. **Rollover**: No trades 20:55-21:05 UTC

## Files

```
overseer/
├── hub.py              # Main entry point
├── .env                # Configuration
├── requirements.txt    # Python dependencies
├── hub/
│   ├── config.py       # Config loader
│   ├── state.py        # State management
│   ├── gates.py        # Gate evaluation
│   ├── telegram.py     # Telegram alerts
│   ├── journal.py      # SQLite journal
│   ├── mt5_client.py   # MT5 integration
│   └── trade_manager.py # Position management
├── scanner/
│   └── OverseerScanner.cs  # Quantower plugin
├── data/
│   ├── state.json      # Persistent state
│   └── trades.db       # SQLite journal
└── tests/
    └── send_mock_signal.py  # Testing
```

## Testing

```bash
# Send mock signal
python tests/send_mock_signal.py

# Expected output:
# [OVERSEER] Signal received: EURUSD UP
# [OVERSEER] PASSED. Quality: 0.78 [B]
# [OVERSEER] Alert fired. Trade #1
```

## Requirements

- Python 3.8+
- Windows 10/11 (for Quantower + MT5)
- Quantower with Rithmic Level 3 MBO subscription
- MT4/MT5 trading account
- Telegram bot token

## Expected Performance

| Metric | Target |
|--------|--------|
| Win Rate | 70-78% |
| Avg RR | 1:2.5 |
| Trades/Week | 5-10 |
| Weekly Return | +5-10% |

---

**Project OVERSEER Forex Edition v12**


# OVERSEER Forex Edition

Toxic Flow Arbitrage Engine for MT4/MT5

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure .env
cp .env.example .env
# Edit .env with your credentials

# 3. Run the hub
python hub.py
```

## Architecture

```
┌─────────────────┐     ZMQ      ┌─────────────────┐     API     ┌──────────┐
│  C# Scanner     │ ──────────▶  │  Python Hub     │ ─────────▶ │ Telegram │
│  (Quantower)    │    JSON      │  (Gate Engine)  │            │  Alerts  │
└─────────────────┘              └─────────────────┘             └──────────┘
                                        │
                                        │ MT5 API
                                        ▼
                                 ┌──────────────┐
                                 │   MT4/MT5    │
                                 │   Broker     │
                                 └──────────────┘
```

## Gate System (94 Total Edges)

### Core Gates (Blocking)

| Gate | Name | Description |
|------|------|-------------|
| I | Circuit Breaker | Halts after 2+ consecutive losses |
| C | Quality Score | Min 0.65 quality required |
| D | Daily Cap | Max 3 trades per day |
| J | Session Window | London/NY hours only (with KZ exceptions) |
| K | Volatility | ATR(14) >= asset minimum |
| E | HTF Alignment | 5-min + 15-min EMA aligned |
| F | Spread Monitor | Live spread <= max threshold |
| H | Tick Momentum | Tick confirmation in signal direction |
| U | DXY Correlation | USD Index alignment |
| Z3 | PD Zone | Premium/Discount zone check |

### Forex-Specific Gates

| Gate | Name | Description |
|------|------|-------------|
| FX-1 | RR Filter | Min 1:1.5 reward:risk ratio |
| FX-2 | Spread Efficiency | Spread < 20% of SL distance |
| FX-3 | Correlation Limit | Max ±2 exposure per currency |
| FX-4 | Rollover Block | No entries 20:55-21:05 UTC |
| FX-10 | Carry Bias | +0.03 bonus for carry-favorable direction |

### Bonus Gates

| Gate | Name | Bonus |
|------|------|-------|
| G | Round Numbers | +0.03 |
| Z6 | Kill Zone | +0.06 |
| Z7 | OTC Lag | +0.10 |
| Z4 | FVG Stack | +0.08 |
| N | Liquidity Pool | +0.08 |

## Signal Flow

```
1. C# Scanner detects Phase 1 candle pattern
2. Gate A (levels) evaluated
3. Gate B (order flow) evaluated - min 6/17
4. Gate K (ATR) check
5. Signal sent via ZMQ to Python Hub
6. Python Hub evaluates remaining gates
7. If passed → Telegram alert + journal log
8. If AUTO_EXECUTE=true → MT5 order placed
```

## Configuration (.env)

```bash
# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# MT5
MT5_ACCOUNT=12345678
MT5_PASSWORD=your_password
MT5_SERVER=ICMarkets-Demo
AUTO_EXECUTE=false

# Risk
RISK_PER_TRADE_PCT=1.0
MAX_DAILY_LOSS_PCT=3.0
MAX_WEEKLY_LOSS_PCT=6.0
MAX_DAILY_TRADES=3

# Gate Thresholds
QUALITY_SCORE_MIN=0.65
GATE_B_MIN_PASS=6
MIN_RR_RATIO=1.5

# ZMQ
ZMQ_PORT=5555
```

## Trade Management

### Position Sizing
- Risk-based: `lots = (balance × risk%) / (SL_pips × pip_value)`
- Default: 1% per trade
- Auto-adjusts for currency pair

### Stop Loss
- Placed at candle wick extreme + buffer
- For UP: SL = wick_low - spread - 1pip
- For DOWN: SL = wick_high + spread + 1pip

### Take Profit
- TP1: 1R (50% position close)
- TP2: 2.5R (remaining position close)
- SL moved to BE after TP1 hit

## Journal Analytics

```bash
# Run analytics
python -c "from hub.journal import print_analytics; print_analytics()"
```

Output:
```
Overall : 45/60 (75.0%) PnL: +$234.50

-- By Gate B Score --
Gate B 14/17: 8 trades, 87.5% WR, +$156.00
Gate B 11/17: 12 trades, 75.0% WR, +$98.00
...
```

## Session Schedule (UTC)

| Session | Start | End |
|---------|-------|-----|
| London | 07:00 | 16:00 |
| NY | 12:00 | 21:00 |
| Overlap | 12:00 | 16:00 |
| Asian | 00:00 | 08:00 |

### Kill Zones
| Zone | Start | End |
|------|-------|-----|
| London Prime | 03:00 | 04:00 |
| NY Open | 09:30 | 10:30 |
| London Close | 11:00 | 12:00 |
| Asian | 20:00 | 21:00 |

## Risk Management

1. **Daily Cap**: Max 3 trades per day
2. **Circuit Breaker**: Halts after 2 consecutive losses
3. **Weekly Cap**: Max 6% weekly loss
4. **Correlation**: Max ±2 exposure per currency
5. **Rollover**: No trades 20:55-21:05 UTC

## Files

```
overseer/
├── hub.py              # Main entry point
├── .env                # Configuration
├── requirements.txt    # Python dependencies
├── hub/
│   ├── config.py       # Config loader
│   ├── state.py        # State management
│   ├── gates.py        # Gate evaluation
│   ├── telegram.py     # Telegram alerts
│   ├── journal.py      # SQLite journal
│   ├── mt5_client.py   # MT5 integration
│   └── trade_manager.py # Position management
├── scanner/
│   └── OverseerScanner.cs  # Quantower plugin
├── data/
│   ├── state.json      # Persistent state
│   └── trades.db       # SQLite journal
└── tests/
    └── send_mock_signal.py  # Testing
```

## Testing

```bash
# Send mock signal
python tests/send_mock_signal.py

# Expected output:
# [OVERSEER] Signal received: EURUSD UP
# [OVERSEER] PASSED. Quality: 0.78 [B]
# [OVERSEER] Alert fired. Trade #1
```

## Requirements

- Python 3.8+
- Windows 10/11 (for Quantower + MT5)
- Quantower with Rithmic Level 3 MBO subscription
- MT4/MT5 trading account
- Telegram bot token

## Expected Performance

| Metric | Target |
|--------|--------|
| Win Rate | 70-78% |
| Avg RR | 1:2.5 |
| Trades/Week | 5-10 |
| Weekly Return | +5-10% |

---

**Project OVERSEER Forex Edition v12**
