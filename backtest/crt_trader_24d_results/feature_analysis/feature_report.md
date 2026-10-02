# CRT feature archaeology

Source: `backtest/crt_trader_24d_results/trades.csv`

> This is a descriptive feature matrix. It does not change CRT/TBS entries and does not select a filter.

## Outcome comparison

| Group | Trades | Win rate | Total R | Avg R | Sweep ATR median | Stop ATR median | Re-entry ATR median |
|---|---:|---:|---:|---:|---:|---:|---:|
| WIN | 49 | 100.00% | 68.2776 | 1.3934 | 0.4336 | 0.8795 | 0.3153 |
| LOSS | 83 | 0.00% | -83.0000 | -1.0000 | 0.4667 | 0.8423 | 0.2617 |

## By pair

| Pair | Trades | Win rate | Total R | Avg R |
|---|---:|---:|---:|---:|
| AUDUSD | 12 | 58.33% | 6.6430 | 0.5536 |
| EURUSD | 21 | 38.10% | -3.7133 | -0.1768 |
| GBPUSD | 14 | 28.57% | -7.6442 | -0.5460 |
| NZDUSD | 22 | 54.55% | 7.7723 | 0.3533 |
| USDCAD | 23 | 34.78% | -2.5773 | -0.1121 |
| USDCHF | 23 | 21.74% | -11.1987 | -0.4869 |
| USDJPY | 17 | 29.41% | -4.0044 | -0.2356 |

## By volatility regime

| Regime | Trades | Win rate | Total R | Avg R |
|---|---:|---:|---:|---:|
| RANGE_CONTRACTION | 68 | 36.76% | 1.0200 | 0.0150 |
| RANGE_EXPANSION | 54 | 33.33% | -13.3760 | -0.2477 |
| TRANSITION | 10 | 60.00% | -2.3664 | -0.2366 |

## By session

| Session | Trades | Win rate | Total R | Avg R |
|---|---:|---:|---:|---:|
| london | 23 | 21.74% | -14.6303 | -0.6361 |
| new_york | 25 | 20.00% | -13.1607 | -0.5264 |
| other | 61 | 39.34% | -1.9768 | -0.0324 |
| overlap | 23 | 65.22% | 15.0454 | 0.6541 |

## Next step

Freeze any candidate feature hypotheses before testing them on a later out-of-sample window.
