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
| Total trades | 21 | 13 |
| Win rate % | 42.857143 | 46.153846 |
| PF | 1.355306 | 1.653623 |
| Total R (raw) | 4.767463 | 5.280165 |
| Total R (weighted) | 0.681066 | 2.813090 |
| Return % | 0.339138 | 1.406980 |
| Max DD % | 0.494856 | 0.306767 |
| Average R (raw) | 0.227022 | 0.406167 |
| Average R (weighted) | 0.032432 | 0.216392 |
| Average exposure % | 6.589060 | 5.855413 |
| Capital utilization % | 6.589060 | 5.855413 |
| Skipped valid opportunities | 10 | 18 |
| Best cycle % | 0.468750 | 1.312500 |
| Worst cycle % | -0.254220 | -0.230928 |

## Allocation diagnostics

- Completed volume cycles: 371
- Equal-weight turnover: 0.000000
- Adaptive turnover (one-way): 30.442663
- equal_weight: average exposure 6.5891%, max exposure 42.8571%, capital utilization 6.5891%.
- equal_weight: skipped valid opportunities 10.
- adaptive: average exposure 5.8554%, max exposure 60.0000%, capital utilization 5.8554%.
- adaptive: skipped valid opportunities 18.

## Output files

- `trades_equal_weight.csv` and `trades_adaptive.csv` contain the full fills/exits.
- `cycle_rankings.csv` contains pair ranking and allocation weight at each completed volume-cycle event.
- `performance_by_cycle.csv` contains performance segmented by cycle event.
- `rolling_performance.csv` contains rolling 20-trade weighted R and return.
- `allocation_weights.csv` contains time-series pair sleeve weights and exposure.
