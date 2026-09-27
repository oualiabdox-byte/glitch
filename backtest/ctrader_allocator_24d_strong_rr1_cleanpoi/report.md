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
| Total trades | 19 | 11 |
| Win rate % | 42.105263 | 45.454545 |
| PF | 1.453694 | 1.890974 |
| Total R (raw) | 5.467967 | 5.980668 |
| Total R (weighted) | 0.781138 | 2.571482 |
| Return % | 0.389405 | 1.284853 |
| Max DD % | 0.462414 | 0.297681 |
| Average R (raw) | 0.287788 | 0.543697 |
| Average R (weighted) | 0.041113 | 0.233771 |
| Average exposure % | 5.470163 | 3.237510 |
| Capital utilization % | 5.470163 | 3.237510 |
| Skipped valid opportunities | 8 | 16 |
| Best cycle % | 0.468750 | 1.312500 |
| Worst cycle % | -0.156812 | -0.230928 |

## Allocation diagnostics

- Completed volume cycles: 371
- Equal-weight turnover: 0.000000
- Adaptive turnover (one-way): 30.442663
- equal_weight: average exposure 5.4702%, max exposure 42.8571%, capital utilization 5.4702%.
- equal_weight: skipped valid opportunities 8.
- adaptive: average exposure 3.2375%, max exposure 48.0000%, capital utilization 3.2375%.
- adaptive: skipped valid opportunities 16.

## Output files

- `trades_equal_weight.csv` and `trades_adaptive.csv` contain the full fills/exits.
- `cycle_rankings.csv` contains pair ranking and allocation weight at each completed volume-cycle event.
- `performance_by_cycle.csv` contains performance segmented by cycle event.
- `rolling_performance.csv` contains rolling 20-trade weighted R and return.
- `allocation_weights.csv` contains time-series pair sleeve weights and exposure.
