# M15 CRT loss analysis — 4H search window

> Baseline: 79 trades. The analysis separates causes; it does not alter production.

## Baseline

| Trades | Win rate | Total R | PF | Max DD R |
|---:|---:|---:|---:|---:|
| 79 | 44.30% | 12.9133 | 1.293483 | 10.8353 |

## Key filter subsets

| Condition | Kept | Win rate | Total R | PF | Max DD R |
|---|---:|---:|---:|---:|---:|
| HTF aligned | 5.06% | 50.00% | 2.6046 | 2.302293 | 1.0000 |
| target <= 6 ATR | 91.14% | 44.44% | 4.1125 | 1.102813 | 11.8268 |
| stop <= 1 ATR | 70.89% | 35.71% | 4.0418 | 1.112272 | 10.8348 |
| sweep <= 0.6 ATR | 72.15% | 35.09% | 9.7916 | 1.264637 | 11.0426 |
| body >= 0.5 | 67.09% | 49.06% | 12.7561 | 1.472449 | 5.6586 |
| reentry penetration >= 0.1 ATR | 74.68% | 45.76% | 6.9089 | 1.215903 | 7.0436 |

## Loss timing

- Losses: **44**; stop losses: **44**.
- Median loss duration: **37.5 minutes**.
- **50.00%** of losing trades ended within 30 minutes.

## Interpretation

- A filter is only a candidate if it improves the kept subset without collapsing the sample; it still needs walk-forward validation.
- HTF alignment and target geometry are evaluated as causal hypotheses; the outcome-path labels are not used as filters.

## Limitations

- HTF bias uses the last completed 2H candle body as a causal approximation, not a full structure engine.
- Single-condition filters are descriptive subsets and do not prove out-of-sample robustness.
- No spread, slippage, commission, or news costs are included.
