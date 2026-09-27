# 14-Day Causal Quality Experiment

Causal signal-quality diagnostic only; scores use data at signal close. Counterfactual outcomes use future bars and are never inputs to scores. This is not yet wired into demo execution.

| Cohort | N | Win rate | Total R | Avg R |
|---|---:|---:|---:|---:|
| A — all canonical valid signals | 24 | 66.67% | 10.3180 | 0.4299 |
| C — top half by market regime score | 12 | 50.00% | -1.4931 | -0.1244 |
| D — top half by liquidity quality | 12 | 50.00% | 2.8287 | 0.2357 |
| E — top half by combined quality | 12 | 58.33% | -0.2332 | -0.0194 |

## Regime breakdown

| Regime | N | Win rate | Total R | Avg R |
|---|---:|---:|---:|---:|
| RANGE_CONTRACTION | 15 | 73.33% | 6.7755 | 0.4517 |
| RANGE_EXPANSION | 5 | 40.00% | -1.2078 | -0.2416 |
| TRANSITION | 4 | 75.00% | 4.7504 | 1.1876 |

The cohorts above are diagnostic selections, not live filters. The combined quality score is not enabled in the demo robot.
