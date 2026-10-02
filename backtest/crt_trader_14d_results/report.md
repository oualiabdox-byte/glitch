# CRT/TBS trader — cTrader 14-day research test

## Configuration

- `{"entry_rule": "body_close_reentry", "execution": "research_only_no_orders", "htf_rule": "2h", "structure_gap": "2-6 M5 candles"}`

## Results

| Pair | Trades | Win rate | Total R | Profit factor | Max DD (R) |
|---|---:|---:|---:|---:|---:|
| AUDUSD | 7 | 57.14% | -0.5050 | 0.831655 | 2.0000 |
| EURUSD | 11 | 45.45% | 2.3290 | 1.388166 | 3.0000 |
| GBPUSD | 7 | 14.29% | -5.1169 | 0.147177 | 5.1169 |
| NZDUSD | 12 | 58.33% | 7.8093 | 2.561865 | 4.4390 |
| USDCAD | 7 | 42.86% | -2.0984 | 0.475388 | 2.0984 |
| USDCHF | 11 | 27.27% | -5.6219 | 0.297265 | 6.5356 |
| USDJPY | 9 | 22.22% | -3.3766 | 0.517632 | 5.0000 |

**Total:** 64 trades, `-6.5805R`.

## Coverage

- GOLD: No local XAUUSD/GC=F cTrader dataset; not substituted

## Caveats

- 14 days is a small research sample
- cTrader trendbar OHLC cannot reveal intrabar stop/target ordering
- the fixture does not contain bid/ask spread or slippage
- this runner does not submit orders or modify execution/demo code
