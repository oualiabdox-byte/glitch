# 14d cTrader M5 Strategy / Allocation Comparison

> The canonical strategy, selector, entry/SL/TP values, 1.5-pip cost, and conservative `sl_first` intrabar policy are unchanged. This is a short research sample, not a profitability claim.

## Data and controls

- Pairs: AUDUSD, EURUSD, GBPUSD, NZDUSD, USDCAD, USDCHF, USDJPY
- Common M5 bars: 2838
- Simulation timeline bars (union across pairs): 2878
- Period: 2026-09-13T21:40:00+00:00 to 2026-09-25T20:55:00+00:00
- Source: cTrader M5 OHLC plus native trendbar volume.
- Entry: next available M5 open after the signal close.
- Risk budget: 0.5% of each pair sleeve; maximum three concurrent positions and one position per pair.
- Equal Weight: 1/7 sleeve weight for every pair.
- Adaptive: Volume-Cycle weights held from cycle completion until the next completed cycle; zero-weight signals are counted as skipped valid opportunities.

## Headline comparison

| Metric | Existing / Equal Weight | Volume-Cycle Adaptive |
|---|---:|---:|
| Total trades | 12 | 10 |
| Win rate % | 66.666667 | 70.000000 |
| PF | 1.940731 | 2.146654 |
| Total R (raw) | 3.114274 | 2.649022 |
| Total R (weighted) | 0.444896 | 1.072935 |
| Return % | 0.222424 | 0.537226 |
| Max DD % | 0.087600 | 0.129007 |
| Average R (raw) | 0.259523 | 0.264902 |
| Average R (weighted) | 0.037075 | 0.107294 |
| Average exposure % | 6.467785 | 8.209980 |
| Capital utilization % | 6.467785 | 8.209980 |
| Skipped valid opportunities | 12 | 14 |
| Best cycle % | 0.104680 | 0.291228 |
| Worst cycle % | -0.086519 | -0.126597 |

## Allocation diagnostics

- Completed volume cycles: 210
- Equal-weight turnover: 0.000000
- Adaptive turnover (one-way): 14.688172
- equal_weight: average exposure 6.4678%, max exposure 42.8571%, capital utilization 6.4678%.
- equal_weight: skipped valid opportunities 12.
- adaptive: average exposure 8.2100%, max exposure 60.0000%, capital utilization 8.2100%.
- adaptive: skipped valid opportunities 14.

## Output files

- `trades_equal_weight.csv` and `trades_adaptive.csv` contain the full fills/exits.
- `cycle_rankings.csv` contains pair ranking and allocation weight at each completed volume-cycle event.
- `performance_by_cycle.csv` contains performance segmented by cycle event.
- `rolling_performance.csv` contains rolling 20-trade weighted R and return.
- `allocation_weights.csv` contains time-series pair sleeve weights and exposure.
