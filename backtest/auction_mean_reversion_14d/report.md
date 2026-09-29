# Strategy B-v1: Auction / Mean-Reversion — 14-day repository dataset

> **Frozen raw baseline.** Source commit `444b9f6c11a5ba0cc4979b954b97682423cec0b0`. Strategy A and the B-v1 rules remain unchanged; future variants must use separate versioned implementations and output directories.

summary["strategy_note"]

## Locked rules and execution controls

- Use only the prior 288 completed M5 bars to define the rolling 24-hour auction range and midpoint.
- Long setup: close back above the prior 12-bar low after sweeping it, at the lower 15% of that range, with bullish rejection.
- Short setup: close back below the prior 12-bar high after sweeping it, at the upper 15% of that range, with bearish rejection.
- Confirm within six bars with a directional close beyond the preceding three-bar pivot; enter at the next M5 open.
- Stop beyond the sweep extreme by max(0.1 x ATR(14), 0.5 pip); target is the range midpoint frozen at sweep; require planned reward/risk >= 1.0.
- One position per pair, maximum 24-hour hold, 1.5-pip round-turn cost, and stop-first handling for ambiguous same-bar stop/target touches.

## Aggregate results

| Metric | Result |
|---|---:|
| Trades | 72 |
| Wins | 22 |
| Losses | 50 |
| Win rate (%) | 30.5556 |
| Profit factor | 0.8685 |
| Gross R | 8.0635 |
| Estimated cost (R) | 16.0473 |
| Net R after cost | -7.9838 |
| Average net R/trade | -0.1109 |
| Max drawdown (R) | 32.9407 |
| Mean planned R:R | 3.3576 |

## Per-pair results

| Pair | Bars | Trades | Win rate (%) | PF | Net R | Max DD (R) |
|---|---:|---:|---:|---:|---:|---:|
| AUDUSD | 2874 | 7 | 14.2857 | 0.1565 | -6.7777 | 8.0350 |
| EURUSD | 2878 | 6 | 50.0000 | 2.4627 | 5.3412 | 3.6516 |
| GBPUSD | 2876 | 13 | 38.4615 | 1.3266 | 3.0693 | 4.6711 |
| NZDUSD | 2877 | 7 | 42.8571 | 1.5171 | 2.5552 | 2.5409 |
| USDCAD | 2878 | 16 | 12.5000 | 0.2196 | -13.3286 | 13.3286 |
| USDCHF | 2839 | 12 | 50.0000 | 1.6297 | 4.6585 | 6.2426 |
| USDJPY | 2877 | 11 | 18.1818 | 0.6564 | -3.5017 | 4.6386 |

## Data coverage

| Pair | Bars | Start UTC | End UTC |
|---|---:|---|---|
| AUDUSD | 2874 | 2026-09-13T21:05:00+00:00 | 2026-09-25T20:55:00+00:00 |
| EURUSD | 2878 | 2026-09-13T21:05:00+00:00 | 2026-09-25T20:55:00+00:00 |
| GBPUSD | 2876 | 2026-09-13T21:05:00+00:00 | 2026-09-25T20:55:00+00:00 |
| NZDUSD | 2877 | 2026-09-13T21:10:00+00:00 | 2026-09-25T20:55:00+00:00 |
| USDCAD | 2878 | 2026-09-13T21:05:00+00:00 | 2026-09-25T20:55:00+00:00 |
| USDCHF | 2839 | 2026-09-13T21:40:00+00:00 | 2026-09-25T20:55:00+00:00 |
| USDJPY | 2877 | 2026-09-13T21:05:00+00:00 | 2026-09-25T20:55:00+00:00 |

## Interpretation limits

14-day research sample only; OHLC cannot establish intrabar order, spreads/slippage vary, the fixed cost is approximate, and these results are not profitability evidence or a recommendation to enable live trading.

The aggregate sums each trade in R and is not a portfolio-equity curve: simultaneous exposure and cross-pair correlation are not modeled. This short sample was not used to tune the locked rules.

Trade-level audit: `trades.csv`; machine-readable results: `summary.json`; frozen specification and input hashes: `v1_baseline.json`.
