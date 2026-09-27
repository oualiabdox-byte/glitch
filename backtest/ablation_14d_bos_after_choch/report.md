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
| Total trades | 10 | 8 |
| Win rate % | 80.000000 | 75.000000 |
| PF | 4.712999 | 4.050470 |
| Total R (raw) | 4.553693 | 3.741155 |
| Total R (weighted) | 0.650528 | 1.082557 |
| Return % | 0.325577 | 0.541618 |
| Max DD % | 0.087600 | 0.129007 |
| Average R (raw) | 0.455369 | 0.467644 |
| Average R (weighted) | 0.065053 | 0.135320 |
| Average exposure % | 2.715179 | 2.278333 |
| Capital utilization % | 2.715179 | 2.278333 |
| Skipped valid opportunities | 7 | 9 |
| Best cycle % | 0.163090 | 0.434660 |
| Worst cycle % | -0.086519 | -0.126597 |

## Allocation diagnostics

- Completed volume cycles: 210
- Equal-weight turnover: 0.000000
- Adaptive turnover (one-way): 14.688172
- equal_weight: average exposure 2.7152%, max exposure 42.8571%, capital utilization 2.7152%.
- equal_weight: skipped valid opportunities 7.
- adaptive: average exposure 2.2783%, max exposure 41.0661%, capital utilization 2.2783%.
- adaptive: skipped valid opportunities 9.

## Output files

- `trades_equal_weight.csv` and `trades_adaptive.csv` contain the full fills/exits.
- `cycle_rankings.csv` contains pair ranking and allocation weight at each completed volume-cycle event.
- `performance_by_cycle.csv` contains performance segmented by cycle event.
- `rolling_performance.csv` contains rolling 20-trade weighted R and return.
- `allocation_weights.csv` contains time-series pair sleeve weights and exposure.
