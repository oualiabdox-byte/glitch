# CRT/TBS trader — cTrader 24d research test

## Configuration

- `{"entry_rule": "body_close_reentry", "execution": "research_only_no_orders", "htf_rule": "2h", "structure_gap": "2-6 M5 candles"}`

## Results

| Pair | Trades | Win rate | Total R | Profit factor | Max DD (R) |
|---|---:|---:|---:|---:|---:|
| AUDUSD | 12 | 58.33% | 6.6430 | 2.328609 | 2.0000 |
| EURUSD | 21 | 38.10% | -3.7133 | 0.714363 | 9.0423 |
| GBPUSD | 14 | 28.57% | -7.6442 | 0.235583 | 7.6442 |
| NZDUSD | 22 | 54.55% | 7.7723 | 1.777231 | 4.4390 |
| USDCAD | 23 | 34.78% | -2.5773 | 0.828183 | 11.8198 |
| USDCHF | 23 | 21.74% | -11.1987 | 0.377851 | 15.5356 |
| USDJPY | 17 | 29.41% | -4.0044 | 0.666303 | 5.3766 |

**Total:** 132 trades, `-14.7224R`.

## Diagnostic funnel

See `diagnostics.csv` and the `diagnostics` field in `summary.json` for per-pair stage counts.

## Coverage

- GOLD: No local XAUUSD/GC=F cTrader dataset; not substituted

## Caveats

- 24d is a limited research sample
- cTrader trendbar OHLC cannot reveal intrabar stop/target ordering
- the fixture does not contain bid/ask spread or slippage
- this runner does not submit orders or modify execution/demo code
