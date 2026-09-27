# 10d cTrader M5 Strategy / Allocation Comparison

> The canonical strategy, selector, entry/SL/TP values, 1.5-pip cost, and conservative `sl_first` intrabar policy are unchanged. This is a short research sample, not a profitability claim.

## Data and controls

- Pairs: AUDUSD, EURUSD, GBPUSD, NZDUSD, USDCAD, USDCHF, USDJPY
- Common M5 bars: 1974
- Simulation timeline bars (union across pairs): 2026
- Period: 2026-09-16T22:15:00+00:00 to 2026-09-25T20:55:00+00:00
- Source: cTrader M5 OHLC plus native trendbar volume.
- Entry: next available M5 open after the signal close.
- Risk budget: 0.5% of each pair sleeve; maximum three concurrent positions and one position per pair.
- Equal Weight: 1/7 sleeve weight for every pair.
- Adaptive: Volume-Cycle weights held from cycle completion until the next completed cycle; zero-weight signals are counted as skipped valid opportunities.

## Headline comparison

| Metric | Existing / Equal Weight | Volume-Cycle Adaptive |
|---|---:|---:|
| Total trades | 8 | 8 |
| Win rate % | 75.000000 | 75.000000 |
| PF | 2.113878 | 3.451562 |
| Total R (raw) | 2.463378 | 5.421707 |
| Total R (weighted) | 0.351911 | 0.721290 |
| Return % | 0.175926 | 0.361097 |
| Max DD % | 0.086519 | 0.024225 |
| Average R (raw) | 0.307922 | 0.677713 |
| Average R (weighted) | 0.043989 | 0.090161 |
| Average exposure % | 5.062756 | 3.138378 |
| Capital utilization % | 5.062756 | 3.138378 |
| Skipped valid opportunities | 9 | 9 |
| Best cycle % | 0.104680 | 0.125806 |
| Worst cycle % | -0.086519 | -0.024225 |

## Allocation diagnostics

- Completed volume cycles: 143
- Equal-weight turnover: 0.000000
- Adaptive turnover (one-way): 10.684136
- equal_weight: average exposure 5.0628%, max exposure 42.8571%, capital utilization 5.0628%.
- equal_weight: skipped valid opportunities 9.
- adaptive: average exposure 3.1384%, max exposure 44.0000%, capital utilization 3.1384%.
- adaptive: skipped valid opportunities 9.

## Output files

- `trades_equal_weight.csv` and `trades_adaptive.csv` contain the full fills/exits.
- `cycle_rankings.csv` contains pair ranking and allocation weight at each completed volume-cycle event.
- `performance_by_cycle.csv` contains performance segmented by cycle event.
- `rolling_performance.csv` contains rolling 20-trade weighted R and return.
- `allocation_weights.csv` contains time-series pair sleeve weights and exposure.
