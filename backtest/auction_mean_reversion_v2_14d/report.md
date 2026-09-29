# Strategy B-v2 — Auction/Mean-Reversion with balanced-regime gate

> Separate experiment. B-v1 remains frozen; Strategy A is unchanged.

## Preregistered single change

- At the completed sweep candle, compute ER(288) from M5 closes: absolute 24-hour net close displacement divided by the sum of absolute close-to-close moves.
- Permit a setup only when ER <= 0.30 (BALANCED); reject the sweep when ER > 0.30 (TRENDING). No other entry, stop, target, execution, cost, or pair-universe rule changes.
- All metrics use the same seven 14d cTrader datasets and estimated 1.5-pip round-turn cost as B-v1.

## Aggregate comparison

| Metric | B-v1 frozen | B-v2 filter | Delta |
|---|---:|---:|---:|
| Trades | 72 | 72 | 0 |
| Win rate (%) | 30.5556 | 30.5556 | 0.0000 |
| Profit factor | 0.8685 | 0.8685 | 0.0000 |
| Gross R | 8.0635 | 8.0635 | 0.0000 |
| Estimated cost (R) | 16.0473 | 16.0473 | 0.0000 |
| Net R | -7.9838 | -7.9838 | 0.0000 |
| Average net R/trade | -0.1109 | -0.1109 | 0.0000 |
| Max drawdown (R) | 32.9407 | 32.9407 | 0.0000 |

## Per-pair results

| Pair | B-v1 trades | B-v2 trades | B-v2 net R | Change in net R | Trending sweeps rejected |
|---|---:|---:|---:|---:|---:|
| AUDUSD | 7 | 7 | -6.7777 | 0.0000 | 0 |
| EURUSD | 6 | 6 | 5.3412 | 0.0000 | 0 |
| GBPUSD | 13 | 13 | 3.0693 | 0.0000 | 0 |
| NZDUSD | 7 | 7 | 2.5552 | 0.0000 | 0 |
| USDCAD | 16 | 16 | -13.3286 | 0.0000 | 0 |
| USDCHF | 12 | 12 | 4.6585 | 0.0000 | 0 |
| USDJPY | 11 | 11 | -3.5017 | 0.0000 | 0 |

## Interpretation limits

Same 14d sample used for this exploratory comparison after B-v1; no out-of-sample validation. The ER threshold was preregistered before this run but the regime hypothesis itself was motivated by B-v1 diagnostics. Costs are estimated; M5 OHLC has intrabar ambiguity.

This is an exploratory same-window comparison, not a proof that the filter generalizes. Aggregate R drawdown is diagnostic only; simultaneous cross-pair exposure is not modeled.

Audit files: `trades.csv`, `summary.json`; rule registration: `backtest/auction_mean_reversion_v2_preregistration.json`.
