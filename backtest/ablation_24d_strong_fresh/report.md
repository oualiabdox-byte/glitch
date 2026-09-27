# 24d cTrader M5 Strategy / Allocation Comparison

> The canonical strategy, selector, entry/SL/TP values, 1.5-pip cost, and conservative `sl_first` intrabar policy are unchanged. This is a short research sample, not a profitability claim.

## Data and controls

- Pairs: AUDUSD, EURUSD, GBPUSD, NZDUSD, USDCAD, USDCHF, USDJPY
- Common M5 bars: 4940
- Simulation timeline bars (union across pairs): 5056
- Period: 2026-09-02T12:05:00+00:00 to 2026-09-25T20:55:00+00:00
- Source: cTrader M5 OHLC plus native trendbar volume.
- Entry: next available M5 open after the signal close.
- Risk budget: 0.5% of each pair sleeve; maximum three concurrent positions and one position per pair.
- Equal Weight: 1/7 sleeve weight for every pair.
- Adaptive: Volume-Cycle weights held from cycle completion until the next completed cycle; zero-weight signals are counted as skipped valid opportunities.

## Headline comparison

| Metric | Existing / Equal Weight | Volume-Cycle Adaptive |
|---|---:|---:|
| Total trades | 33 | 22 |
| Win rate % | 57.575758 | 59.090909 |
| PF | 1.407381 | 1.771619 |
| Total R (raw) | 5.708211 | 6.739961 |
| Total R (weighted) | 0.815459 | 3.680191 |
| Return % | 0.406644 | 1.847172 |
| Max DD % | 0.432225 | 0.412486 |
| Average R (raw) | 0.172976 | 0.306362 |
| Average R (weighted) | 0.024711 | 0.167281 |
| Average exposure % | 10.236777 | 7.808348 |
| Capital utilization % | 10.236777 | 7.808348 |
| Skipped valid opportunities | 28 | 39 |
| Best cycle % | 0.468750 | 1.312500 |
| Worst cycle % | -0.156812 | -0.248399 |

## Allocation diagnostics

- Completed volume cycles: 371
- Equal-weight turnover: 0.000000
- Adaptive turnover (one-way): 30.442663
- equal_weight: average exposure 10.2368%, max exposure 42.8571%, capital utilization 10.2368%.
- equal_weight: skipped valid opportunities 28.
- adaptive: average exposure 7.8083%, max exposure 60.0000%, capital utilization 7.8083%.
- adaptive: skipped valid opportunities 39.

## Output files

- `trades_equal_weight.csv` and `trades_adaptive.csv` contain the full fills/exits.
- `cycle_rankings.csv` contains pair ranking and allocation weight at each completed volume-cycle event.
- `performance_by_cycle.csv` contains performance segmented by cycle event.
- `rolling_performance.csv` contains rolling 20-trade weighted R and return.
- `allocation_weights.csv` contains time-series pair sleeve weights and exposure.
