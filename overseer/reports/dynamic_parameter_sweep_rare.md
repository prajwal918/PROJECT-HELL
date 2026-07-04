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
| 6AM6 | BUY | 100.00% | 8/0/0 | 8 | 48.96% | `adjusted_score <= 0.9` |
| 6BM6 | BUY | 100.00% | 6/0/5 | 11 | 67.50% | `l3.l3_confidence >= 0.819931; fw.FW01_multi_tf_trend >= 0.05` |
| 6EM6 | BUY | 85.71% | 6/1/24 | 31 | 38.89% | `fw.FW06_session_kz <= 0; fw.FW03_volume <= 0.2222` |
| 6EM6 | SELL | 85.71% | 6/1/28 | 35 | 38.10% | `l3.l3_confidence <= 0.630139; l3.hft_synchronized_volume <= 3852; bias.l3_bias >= 0.4` |
| 6JM6 | BUY | 85.71% | 6/1/15 | 22 | 18.18% | `l3.hft_synchronized_volume >= 4809; fw.FW15_l3_flow <= 0` |
| 6BM6 | SELL | 80.00% | 4/1/1 | 6 | 35.29% | `fw.FW15_l3_flow >= 0.05; l3.l3_confidence <= 0.6` |
| 6AM6 | SELL | 75.00% | 6/2/33 | 41 | 66.67% | `l3.l3_prediction <= -1` |
| 6CM6 | BUY | 40.00% | 6/9/4 | 19 | 65.00% | `l3.l3_confidence >= 0.95; l3.hft_signal >= 0.05` |
| 6JM6 | SELL | 0.00% | 0/12/29 | 41 | 0.00% | `fw.FW10_post_news <= 0.5; bias.raw_bias <= 0.817745; l3.hft_synchronized_volume >= 784` |

## Recommended Use

1. Keep `AUTO_EXECUTE=false` while testing these parameters.
2. Only promote filters that stay strong on fresh forward data.
3. Prefer filters with at least 30 validation non-flat outcomes.
4. If validation WR is high but total count is tiny, treat it as fragile.
5. Do not use raw model score alone; current live data shows score drift.
