# CRT-SMC Hybrid Soft Layer — 24 days

> All 132 CRT trades are preserved. SMC evidence creates a quality score; it does not reject trades.

## Overall

| Mode | Trades | Win rate | Total R | Avg R | PF | Max DD R |
|---|---:|---:|---:|---:|---:|---:|
| CRT baseline / equal risk | 132 | 37.12% | -14.7224 | -0.1115 | 0.822622 | 26.9538 |
| Research soft sizing | 132 | 37.12% | -10.2559 | -0.0777 | 0.852434 | 22.8869 |

## Quality bands

| Band | Trades | Mean score | Win rate | Total R | PF | Max DD R |
|---|---:|---:|---:|---:|---:|---:|
| BALANCED | 48 | 45.43 | 56.25% | 9.8826 | 1.470598 | 8.8643 |
| WEAK | 79 | 22.95 | 26.58% | -21.2356 | 0.633869 | 28.4243 |
| STRONG | 5 | 76.77 | 20.00% | -3.3694 | 0.157652 | 3.0000 |

## Design

The CRT rules remain the candidate generator. HTF alignment, causal BOS, pre-entry displacement, and nearby FVG/OB evidence are scored softly. A later walk-forward study may use the score for position-size modulation, but not for deleting setups.

## Limitations

- FVG/OB detectors are causal research approximations, not the incomplete production SMC engine.
- The score is descriptive and has not been walk-forward validated.
- Soft sizing is shown as a research scenario, not a trading recommendation.
- No spread, slippage, commission, or news costs are included.
