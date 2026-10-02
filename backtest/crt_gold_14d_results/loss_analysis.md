# Gold CRT/TBS loss analysis

## Scope

- Instrument: `GOLD`
- Data: Yahoo Finance `GC=F` proxy, 5-minute OHLC
- Period: 2026-09-18 through 2026-10-02
- Sample: 12 trades, 8 losses, 4 winners
- This is an exploratory diagnosis of one short sample, not a validated optimization.

## Main finding

All eight losing trades exited at the hard stop. **None reached CRT equilibrium before stopping.** Therefore, the current evidence does not identify the breakeven rule as the cause of the losses. The first adjustment target should be **entry quality and confirmation strength**, while exit management should be tested separately.

Seven of the eight losses stopped within approximately one hour of entry. Five of eight reached at least 0.5R of favorable excursion but still failed to reach equilibrium; this suggests some entries experienced an initial reaction but did not produce a sufficiently durable reversal.

## Loss-by-loss diagnosis

| Entry UTC | Side | Gap | Time to stop | MFE | Approximate interpretation |
|---|---|---:|---:|---:|---|
| 2026-09-23 17:05 | Long | 6 | 35 min | 0.73R | Wide six-candle structure; large sweep/risk relative to ATR; reversal did not reach equilibrium. |
| 2026-09-23 23:55 | Short | 4 | 5 min | 0.09R | Immediate failure; weak favorable follow-through after re-entry. |
| 2026-09-24 18:55 | Short | 6 | 3 h 5 min | 1.32R | Initial favorable move, but no equilibrium; later invalidation. |
| 2026-09-29 05:10 | Short | 2 | 5 min | 0.88R | Immediate rejection after a small-gap setup; confirmation did not persist. |
| 2026-09-29 10:50 | Short | 2 | 5 min | 0.48R | Immediate failure; re-entry penetration was very shallow. |
| 2026-09-30 07:25 | Short | 2 | 55 min | 0.59R | Favorable reaction but no equilibrium; larger relative risk and sweep excursion. |
| 2026-09-30 18:50 | Long | 3 | 5 min | 0.05R | Immediate failure; almost no follow-through. |
| 2026-10-01 19:20 | Short | 2 | 30 min | 3.11R | Strong initial favorable move, then a large reversal; exit/target path needs separate testing. |

## What separates losses from winners in this sample?

| Feature | Losses | Winners | Interpretation |
|---|---:|---:|---|
| Count | 8 | 4 | Too small for statistical inference |
| Average structure gap | 3.375 | 3.500 | No useful separation |
| Median MFE | 0.66R | 5.15R | Winners followed through much more strongly |
| Median MAE | 1.07R | 0.21R | Losing setups moved adversely earlier and more deeply |
| Average initial risk / M5 ATR | 0.95 | 0.71 | Larger relative risk is a warning candidate |
| Average sweep excursion / M5 ATR | 0.64 | 0.40 | Oversized sweeps look more fragile |
| Equilibrium reached | 0/8 | 4/4 | Strongest observed distinction |

The 2–6 candle rule did not separate winners from losers: both groups contained short-gap and long-gap setups. Session hour also did not separate them reliably; winners occurred around 15:00–20:35 UTC and losses occurred in overlapping hours.

## Entry-filter counterfactuals

These are **in-sample diagnostics only**. They are not evidence that the thresholds generalize.

| Hypothesis | Trades retained | Losses retained | Winners retained | Total R in this sample |
|---|---:|---:|---:|---:|
| Current rules | 12 | 8 | 4 | +4.7909R |
| Initial risk <= 1.2 M5 ATR | 10 | 6 | 4 | +6.791R |
| Sweep excursion <= 0.6 M5 ATR | 8 | 4 | 4 | +8.791R |
| Re-entry penetration >= 0.15 M5 ATR | 9 | 6 | 3 | +5.765R |
| Gap >= 3 | 7 | 4 | 3 | +2.722R |

The most promising **hypothesis** is to reject unusually deep sweeps, because this threshold removed four losses and no winners in this tiny sample. The second is to reject trades whose initial stop distance is unusually large relative to M5 ATR.

However, choosing `0.6 ATR` or `1.2 ATR` after observing these 12 trades would be overfitting. These values must be frozen before a longer walk-forward test.

## Exit-management conclusion

The current management rule is not implicated in the eight losses:

- all eight stopped before TP1;
- none reached equilibrium;
- breakeven was never activated on a losing trade.

Changing breakeven alone is therefore unlikely to fix this loss group. The exception is the 2026-10-01 trade, which reached approximately 3.1R favorable excursion and later stopped. That is a separate trailing/target-management question, not evidence that the entire exit model is wrong.

## Recommended next experiment

Do not change several rules at once. Run a predeclared A/B walk-forward test on a materially longer Gold sample:

1. Baseline CRT/TBS rules.
2. Baseline plus `sweep excursion <= 0.6 ATR`.
3. Baseline plus `initial risk <= 1.2 ATR`.
4. Baseline plus both filters.
5. Keep the current exit model initially.
6. Separately compare no-breakeven, current breakeven, and a conservative trailing rule.

For each arm, report trades/day, expectancy, profit factor, max drawdown, longest losing streak, total R, and results before/after realistic spread and slippage. Select a rule only if it improves out-of-sample robustness rather than this 14-day in-sample total.

## Conclusion

The strongest actionable diagnosis is:

> **The CRT/TBS entry accepts reversals that are too deep or too unstable relative to recent Gold volatility.**

The first research modification should therefore be an entry-quality filter based on sweep excursion and/or initial risk normalized by ATR. Do not start by changing breakeven. Do not deploy the filter from this sample alone.
