# CRT-SMC executable hybrid — 24 days

> Every CRT candidate is preserved. Structural stop and causal target alter management; HTF/FVG alter only soft risk.

| Variant | Trades | Win rate | Total R | Avg R | PF | Max DD R |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 132 | 37.12% | -14.7224 | -0.1115 | 0.822622 | 26.9538 |
| structural_stop_path_target | 132 | 41.67% | -2.3064 | -0.0175 | 0.958562 | 18.8944 |
| hybrid_htf025 | 132 | 41.67% | 4.4793 | 0.0339 | 1.2242 | 4.3084 |
| hybrid_htf025_fvg075 | 132 | 41.67% | 4.6238 | 0.0350 | 1.264564 | 3.9437 |

## Implementation counts

- target_crt_boundary: 68
- target_causal_swing: 64
- target_equilibrium_fallback: 0
- structural_stop_available: 127
- htf_aligned: 38
- fvg_near_entry: 67

## Limitations

- The target is causal only from confirmed pre-entry pivots; it is not a full opposing-liquidity engine.
- FVG/OB are evidence/risk features here, not a delayed retest-entry model.
- Risk multipliers are hypotheses and must be walk-forward validated.
- No spread, slippage, commission, or news data are in the fixtures.
