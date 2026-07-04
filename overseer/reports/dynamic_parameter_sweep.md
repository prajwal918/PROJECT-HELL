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
| 6EM6 | BUY | 76.47% | 13/4/61 | 78 | 41.89% | `fw.FW06_session_kz <= 0` |
| 6AM6 | BUY | 73.91% | 17/6/28 | 51 | 43.75% | `bias.l3_bias <= 0.5; bias.raw_bias <= 0.5` |
| 6BM6 | BUY | 70.00% | 7/3/7 | 17 | 67.86% | `l3.hft_signal >= 0.05; l3.l3_confidence >= 0.8` |
| 6EM6 | SELL | 70.00% | 7/3/33 | 43 | 33.33% | `l3.l3_confidence <= 0.68448; fw.FW06_session_kz <= 0; bias.l3_bias >= 0.4` |
| 6JM6 | BUY | 61.54% | 8/5/38 | 51 | 15.79% | `l3.hft_synchronized_volume >= 4105` |
| 6AM6 | SELL | 54.55% | 6/5/48 | 59 | 53.12% | `l3.l3_prediction <= 0` |
| 6BM6 | SELL | 50.00% | 6/6/5 | 17 | 29.03% | `bias.l3_bias <= 0.517831; score <= 0.657138; bias.raw_bias <= 0.58407` |
| 6CM6 | BUY | 27.27% | 6/16/4 | 26 | 61.11% | `l3.hft_signal >= 0.05; l3.l3_confidence >= 0.9` |
| 6JM6 | SELL | 0.00% | 0/16/50 | 66 | 1.96% | `fw.FW10_post_news <= 0.5` |

## Recommended Use

1. Keep `AUTO_EXECUTE=false` while testing these parameters.
2. Only promote filters that stay strong on fresh forward data.
3. Prefer filters with at least 30 validation non-flat outcomes.
4. If validation WR is high but total count is tiny, treat it as fragile.
5. Do not use raw model score alone; current live data shows score drift.
