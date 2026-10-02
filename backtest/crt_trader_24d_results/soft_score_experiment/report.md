# CRT soft-score ablation (24 days)

> Research-only counterfactual. CRT generation, adapter behavior, and trailer behavior were not changed.

| Experiment | Trades | Win rate | Total R | Avg R | Profit factor |
|---|---:|---:|---:|---:|---:|
| raw_crt | 132 | 37.12% | -14.7224 | -0.1115 | 0.8226 |
| overlap_only | 23 | 65.22% | 15.0454 | 0.6541 | 2.8807 |
| range_contraction_only | 68 | 36.76% | 1.0200 | 0.0150 | 1.0237 |
| soft_score_ge_0_60 | 56 | 37.50% | 3.2754 | 0.0585 | 1.0936 |
| soft_score_ge_0_70 | 21 | 61.90% | 17.8911 | 0.8520 | 3.2364 |

## Interpretation

The score is an evaluation layer, not a live filter. A positive result here does not measure missed CRT candidates and does not establish robustness.
The next validation must freeze the score definition and test it on a later out-of-sample window.
