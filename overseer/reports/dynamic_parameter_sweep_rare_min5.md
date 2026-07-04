# Dynamic Parameter Sweep

This report uses a time-ordered train/validation split from `signal_log`.
It is a research filter report, not a live-trading guarantee.

## Overall Signal Journal

- Total labeled signals: 8816
- Non-flat outcomes: 2972
- WIN/LOSS/FLAT: 1030/1942/5844
- WR excluding FLAT: 34.66%
- WR including FLAT: 11.68%

## Best Dynamic Filters By Symbol/Direction

| Symbol | Direction | Val WR ex-FLAT | Val W/L/F | Val total | Train WR ex-FLAT | Rules |
|---|---:|---:|---:|---:|---:|---|
| 6CM6 | SELL | 100.00% | 16/0/37 | 53 | 100.00% | `l3.l3_confidence >= 0.475959; l3.hft_synchronized_volume >= 2875` |
| 6AM6 | BUY | 100.00% | 8/0/0 | 8 | 48.96% | `adjusted_score <= 0.9` |
| 6AM6 | SELL | 100.00% | 5/0/17 | 22 | 60.00% | `l3.l3_prediction <= -1; l3.l3_confidence <= 0.714229; bias.l3_bias <= 0.579345` |
| 6JM6 | BUY | 100.00% | 5/0/17 | 22 | 0.00% | `l3.hft_synchronized_volume >= 7549` |
| 6BM6 | BUY | 85.71% | 6/1/7 | 14 | 77.78% | `l3.l3_confidence >= 0.819931; fw.FW15_l3_flow <= 0; bias.l3_bias >= 0.8` |
| 6EM6 | BUY | 85.71% | 6/1/24 | 31 | 38.89% | `fw.FW06_session_kz <= 0; fw.FW03_volume <= 0.2222` |
| 6EM6 | SELL | 85.71% | 6/1/13 | 20 | 20.00% | `l3.l3_confidence <= 0.630139; l3.hft_synchronized_volume <= 1011; bias.l3_bias <= 0.613924` |
| 6BM6 | SELL | 80.00% | 4/1/1 | 6 | 47.37% | `fw.FW15_l3_flow >= 0.05; l3.l3_confidence <= 0.6; fw.FW06_session_kz <= 0` |
| 6CM6 | BUY | 55.56% | 5/4/27 | 36 | 90.00% | `fw.FW04_liquidity_sweep <= 0.3448` |
| 6JM6 | SELL | 0.00% | 0/15/24 | 39 | 0.00% | `score <= 0.196555; bias.raw_bias <= 0.817745; fw.FW10_post_news <= 0.5` |

## Dynamic 90% Selector Classification

Runtime policy: all classifications are signal-only. Live execution remains disabled; promotion requires fresh forward validation.

| Status | Symbol | Direction | Val WR ex-FLAT | Val W/L/F | Baseline Val W/L/F | Rules | Reason |
|---|---|---:|---:|---:|---:|---|---|
| TRADE_CANDIDATE_SIGNAL_ONLY | 6CM6 | SELL | 100.00% | 16/0/37 | 55/3/184 | `l3.l3_confidence >= 0.475959; l3.hft_synchronized_volume >= 2875` | baseline validation WR ex-FLAT 94.83% with nonflat=58; elite validation WR ex-FLAT 100.00% with nonflat=16 |
| WATCHLIST | 6AM6 | BUY | 100.00% | 8/0/0 | 74/138/127 | `adjusted_score <= 0.9` | validation WR ex-FLAT 100.00% but nonflat=8<30 |
| WATCHLIST | 6AM6 | SELL | 100.00% | 5/0/17 | 7/40/119 | `l3.l3_prediction <= -1; l3.l3_confidence <= 0.714229; bias.l3_bias <= 0.579345` | validation WR ex-FLAT 100.00% but nonflat=5<30 |
| WATCHLIST | 6JM6 | BUY | 100.00% | 5/0/17 | 22/46/172 | `l3.hft_synchronized_volume >= 7549` | validation WR ex-FLAT 100.00% but nonflat=5<30 |
| BLOCK | 6BM6 | BUY | 85.71% | 6/1/7 | 49/288/71 | `l3.l3_confidence >= 0.819931; fw.FW15_l3_flow <= 0; bias.l3_bias >= 0.8` | validation WR ex-FLAT 85.71% with nonflat=7 |
| BLOCK | 6BM6 | SELL | 80.00% | 4/1/1 | 12/81/80 | `fw.FW15_l3_flow >= 0.05; l3.l3_confidence <= 0.6; fw.FW06_session_kz <= 0` | validation WR ex-FLAT 80.00% with nonflat=5 |
| BLOCK | 6CM6 | BUY | 55.56% | 5/4/27 | 18/389/67 | `fw.FW04_liquidity_sweep <= 0.3448` | validation WR ex-FLAT 55.56% with nonflat=9 |
| BLOCK | 6EM6 | BUY | 85.71% | 6/1/24 | 37/40/195 | `fw.FW06_session_kz <= 0; fw.FW03_volume <= 0.2222` | validation WR ex-FLAT 85.71% with nonflat=7 |
| BLOCK | 6EM6 | SELL | 85.71% | 6/1/13 | 7/11/152 | `l3.l3_confidence <= 0.630139; l3.hft_synchronized_volume <= 1011; bias.l3_bias <= 0.613924` | validation WR ex-FLAT 85.71% with nonflat=7 |
| BLOCK | 6JM6 | SELL | 0.00% | 0/15/24 | 0/20/146 | `score <= 0.196555; bias.raw_bias <= 0.817745; fw.FW10_post_news <= 0.5` | validation WR ex-FLAT 0.00% with nonflat=15 |

## Recommended Use

1. Keep `AUTO_EXECUTE=false` while testing these parameters.
2. Only promote filters that stay strong on fresh forward data.
3. Prefer filters with at least 30 validation non-flat outcomes.
4. If validation WR is high but total count is tiny, treat it as fragile.
5. Do not use raw model score alone; current live data shows score drift.
