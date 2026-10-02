# CRT raw loss-fix ablation (24 days)

> Research-only. CRT generation, adapter behavior, and trailer behavior were not changed.

| Experiment | Trades | Win rate | Total R | Avg R | PF |
|---|---:|---:|---:|---:|---:|
| raw_current_exit | 132 | 37.12% | -14.7224 | -0.1115 | 0.8226 |
| long_only | 53 | 43.40% | 5.4286 | 0.1024 | 1.1810 |
| short_only | 79 | 32.91% | -20.1510 | -0.2551 | 0.6198 |
| overlap_only | 23 | 65.22% | 15.0454 | 0.6541 | 2.8807 |
| long_overlap | 12 | 83.33% | 16.1057 | 1.3421 | 9.0529 |
| non_expansion | 78 | 39.74% | -1.3464 | -0.0173 | 0.9714 |
| equilibrium_exit_all | 132 | 27.27% | -43.5865 | -0.3302 | 0.5460 |
| equilibrium_exit_overlap | 23 | 43.48% | 5.8334 | 0.2536 | 1.4487 |
| equilibrium_exit_long | 53 | 37.74% | -4.0027 | -0.0755 | 0.8787 |

## Pair breakdown — current exit

| Pair | Trades | Win rate | Total R | PF |
|---|---:|---:|---:|---:|
| AUDUSD | 12 | 58.33% | 6.6430 | 2.3286 |
| EURUSD | 21 | 38.10% | -3.7133 | 0.7144 |
| GBPUSD | 14 | 28.57% | -7.6442 | 0.2356 |
| NZDUSD | 22 | 54.55% | 7.7723 | 1.7772 |
| USDCAD | 23 | 34.78% | -2.5773 | 0.8282 |
| USDCHF | 23 | 21.74% | -11.1987 | 0.3779 |
| USDJPY | 17 | 29.41% | -4.0044 | 0.6663 |

## Interpretation

Direction and session filters are selection hypotheses. Equilibrium exit is a separate exit experiment and must be compared with realistic spread/slippage before any promotion.
