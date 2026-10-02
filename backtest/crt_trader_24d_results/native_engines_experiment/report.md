# CRT-native alternative engines (24 days)

> Research-only comparison. These engines do not use the original SMC engine and do not modify CRT generation.

| Engine | Trades | Win rate | Total R | Avg R | Profit factor |
|---|---:|---:|---:|---:|---:|
| crt_raw | 132 | 37.12% | -14.7224 | -0.1115 | 0.8226 |
| session_liquidity_overlap | 23 | 65.22% | 15.0454 | 0.6541 | 2.8807 |
| volatility_compression | 68 | 36.76% | 1.0200 | 0.0150 | 1.0237 |
| sweep_risk_normalization | 85 | 35.29% | -8.8610 | -0.1042 | 0.8389 |
| reentry_momentum | 57 | 35.09% | -2.9598 | -0.0519 | 0.9200 |
| overlap_sweep_confirmation | 15 | 53.33% | 7.0192 | 0.4679 | 2.0027 |
| compression_sweep_confirmation | 58 | 39.66% | 1.6599 | 0.0286 | 1.0474 |
| overlap_reentry_momentum | 8 | 75.00% | 6.5104 | 0.8138 | 4.2552 |

## Recommendation for next validation

Freeze the best two candidates by mechanism, not by total R alone, then run both on a later out-of-sample period.
Do not combine all conditions yet: very small samples can create an attractive but unstable result.
