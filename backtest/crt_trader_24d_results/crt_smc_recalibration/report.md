# CRT-SMC quality recalibration — walk-forward

> All CRT trades remain. Only classification thresholds and soft risk multipliers are recalibrated.

## Baseline

`{"avg_r": -0.111533, "max_drawdown_r": 27.953797, "profit_factor": 0.822622, "total_r": -14.722405, "trades": 132, "win_rate_pct": 37.12}`

## Walk-forward results

| Fold | Low | High | Weak x | Balanced x | Strong x | Test Total R | Test PF | Test Max DD R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| train_first_half_test_second_half | 40 | 50 | 0.25 | 1.0 | 1.0 | -3.697138 | 0.785673 | 7.272921 |
| train_first_75_test_last_25 | 40 | 50 | 0.25 | 1.0 | 1.0 | -4.389272 | 0.537971 | 7.272921 |

## Consensus

- Boundaries: `WEAK < 40`, `BALANCED 40–50`, `STRONG >= 50`.
- Multipliers: `WEAK=0.25`, `BALANCED=1.0`, `STRONG=1.0`.
- Descriptive full-sample result: `{"avg_r": 0.050086, "max_drawdown_r": 10.493664, "profit_factor": 1.201872, "total_r": 6.611295, "trades": 132, "win_rate_pct": 37.12}`.

## Important

A positive soft-sized result would not mean the original CRT expectancy became positive; it means risk was allocated differently across the same trades. The decision must be based on the later walk-forward segments, not the full-sample descriptive result.

## Limitations

- Only 132 trades over 24 days; thresholds are not production settings.
- Walk-forward folds are small and use the same limited dataset for research.
- The objective can optimize risk allocation, not the underlying trade expectancy; unweighted CRT remains unchanged.
- No spread, slippage, commission, or news costs are included.
