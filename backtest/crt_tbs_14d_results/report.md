# CRT/TBS 14-day research backtest

Period: `2026-09-18T14:40:00+00:00` to `2026-10-02T14:40:00+00:00`

## Rules

- 2-hour CRT candle; next completed candle must sweep one boundary and close back inside.
- On the following 2-hour bucket, detect a lower-timeframe TBS: equal highs/lows 2–6 M5 candles apart, body close beyond the level, then close back through it.
- Stop beyond sweep extreme; take 50% at CRT equilibrium, move remainder to breakeven, target opposite CRT boundary.

## Results

| Instrument | Trades | Win rate | Total R | Profit factor | Max DD (R) |
|---|---:|---:|---:|---:|---:|
| EURUSD | 2 | 50.00% | 0.0328 | 1.0328 | 1.0000 |
| GBPUSD | 16 | 18.75% | -7.8185 | 0.3986 | 8.2179 |
| USDJPY | 12 | 25.00% | -5.1351 | 0.4294 | 6.0000 |
| GOLD | 12 | 33.33% | 4.7909 | 1.5989 | 3.0000 |

**Total:** 42 trades, `-8.1299R`.

## Caveats

- 14 calendar days is a small sample
- Yahoo OHLC is indicative and not bid/ask executable
- GC=F is a gold-futures proxy, not broker-specific XAUUSD
- no spread, slippage, commission, or financing modeled
- intrabar stop/target ordering is conservative but still unknowable from OHLC
