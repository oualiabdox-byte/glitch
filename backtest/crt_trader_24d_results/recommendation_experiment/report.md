# CRT recommendation and target experiment (24 days)

> Research-only. The recommended filter removes USDCHF/GBPUSD and retains Overlap/Other sessions. No live path changed.

| Experiment | Trades | Win rate | Total R | Avg R | PF |
|---|---:|---:|---:|---:|---:|
| raw_current_exit | 132 | 37.12% | -14.7224 | -0.1115 | 0.8226 |
| exclude_bad_pairs | 95 | 42.11% | 4.1204 | 0.0434 | 1.0749 |
| overlap_or_other | 84 | 46.43% | 13.0686 | 0.1556 | 1.2904 |
| recommended_filter | 59 | 54.24% | 23.1042 | 0.3916 | 1.8557 |
| recommended_stop_le_1.2atr | 41 | 56.10% | 23.4918 | 0.5730 | 2.3051 |
| recommended_sweep_le_0.8atr | 45 | 53.33% | 21.1404 | 0.4698 | 2.0067 |
| recommended_target_le_6atr | 40 | 67.50% | 27.1291 | 0.6782 | 3.0869 |
| recommended_target_le_6_stop_le_1.2 | 32 | 68.75% | 26.4531 | 0.8267 | 3.6453 |
| recommended_reentry_ge_0.30atr | 33 | 54.55% | 3.5924 | 0.1089 | 1.2395 |
| recommended_target_2r | 59 | 28.81% | -8.9592 | -0.1519 | 0.7867 |
| recommended_target_3r | 59 | 22.03% | -9.5948 | -0.1626 | 0.7914 |
| recommended_tp1_rest_original | 59 | 11.86% | -4.6127 | -0.0782 | 0.8643 |
| recommended_multi_target | 59 | 22.03% | -21.0207 | -0.3563 | 0.3817 |

## Target-distance diagnosis

Original target median: 6.10R; losses median: 7.17R; wins median: 4.21R.

The 2R/3R caps and multi-target variants were negative because they use the initial stop and remove the original system's breakeven/large-target payoff behavior. This is evidence against a simple fixed 2R replacement, not proof that every partial-exit design fails.

The recommended pair/session filter leaves 59 trades and +23.10R. Entry-side filters show that stop <= 1.2 ATR leaves 41 trades and +23.49R, while target distance <= 6 ATR leaves 40 trades and +27.13R. Combining them leaves only 32 trades; these are in-sample hypotheses, not production rules.

The re-entry penetration >= 0.30 ATR filter leaves 33 trades but only +3.59R, so stronger re-entry depth alone is not supported by this sample.

The multi-target variants are descriptive exit experiments and must be validated with new data, spread, and slippage.
