# Volume-Cycle Adaptive Allocator Backtest

> This is a research backtest on cTrader trendbar OHLC plus native tick volume. It is not an execution or profitability guarantee.

## Method

- Each pair forms a cycle when cumulative positive volume reaches the median prior-volume quota multiplied by `cycle_bars`.
- The first warm-up window is calibration-only.
- A completed cycle contributes its close-to-close return to that pair's history.
- Weights for the next bar use only previously completed cycles; no future bar is used.
- Positive EWMA cycle momentum is scaled by mean absolute cycle return, capped per pair, and normalized.
- The benchmark is equal weight across all available pairs at every bar.

## Data

- Pairs: AUDUSD, EURUSD, GBPUSD, NZDUSD, USDCAD, USDCHF, USDJPY
- Common M5 timestamps: 1974
- Common period: 2026-09-16T22:15:00+00:00 to 2026-09-25T20:55:00+00:00
- Completed volume cycles: 143

## Results

| Portfolio | Total return | Max drawdown | Win rate | Unannualized Sharpe | Bars |
|---|---:|---:|---:|---:|---:|
| Adaptive | 0.3273% | -0.6574% | 50.40567951318459% | 0.011982274025249788 | 1973 |
| Equal weight | -0.2120% | -0.5090% | 51.03902686264572% | -0.013986487907220605 | 1973 |

## Reproducibility

- Configuration: `{"ewma_alpha": 0.35, "history_cycles": 6, "max_weight": 0.4, "target_cycle_bars": 96, "temperature": 0.5, "vol_floor": 0.0005, "volume_lookback_bars": 96, "warmup_bars": 96}`
- The input JSON files are retained under `backtest/ctrader_volume_data/` for subsequent runs.
- Results are saved as JSON, CSV, and Markdown in the output directory.
