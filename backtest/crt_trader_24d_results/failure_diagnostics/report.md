# CRT failure diagnostics — 24 days

> Diagnostic variants only; canonical CRT signals were not modified.

## Exit and stop variants

| Variant | Trades | Win rate | Total R | Avg R | PF | Max DD R |
|---|---:|---:|---:|---:|---:|---:|
| baseline_current | 132 | 37.12% | -14.7224 | -0.1115 | 0.822622 | 26.9538 |
| wider_stop_0.25_atr | 132 | 41.67% | -12.2278 | -0.0926 | 0.816745 | 21.3406 |
| structural_stop | 132 | 41.67% | -4.4517 | -0.0337 | 0.920018 | 19.3055 |
| no_breakeven | 132 | 21.21% | -22.9646 | -0.1740 | 0.756038 | 43.1520 |
| full_exit_equilibrium | 132 | 37.12% | -6.2551 | -0.0474 | 0.924638 | 27.7877 |
| nearest_swing_beyond_eq | 132 | 37.12% | 18.5349 | 0.1404 | 1.223313 | 20.4346 |

## Baseline groups

| Group | Trades | Win rate | Total R | PF | Max DD R |
|---|---:|---:|---:|---:|---:|
| htf_alignment=False | 94 | 26.60% | -30.4325 | 0.558949 | 35.7413 |
| htf_alignment=True | 38 | 63.16% | 15.7101 | 2.12215 | 5.3103 |
| fvg_near_entry=False | 65 | 29.23% | -16.4259 | 0.642915 | 23.4936 |
| fvg_near_entry=True | 67 | 44.78% | 1.7035 | 1.046041 | 15.4821 |
| ob_near_entry=False | 1 | 100.00% | 0.5429 | None | 0.0000 |
| ob_near_entry=True | 131 | 36.64% | -15.2653 | 0.816081 | 27.4967 |
| path=EQ_THEN_BE | 36 | 100.00% | 27.0513 | None | 0.0000 |
| path=EQ_THEN_TARGET | 13 | 100.00% | 41.2263 | None | 0.0000 |
| path=STOP_BEFORE_EQ | 83 | 0.00% | -83.0000 | 0.0 | 82.0000 |

## Execution cost sensitivity

| Cost per trade | Total R | PF | Max DD R |
|---|---:|---:|---:|
| 0.02R | -17.3624 | 0.794957 | 28.7938 |
| 0.05R | -21.3224 | 0.755596 | 31.8450 |
| 0.10R | -27.9224 | 0.695129 | 37.2450 |
| 0.15R | -34.5224 | 0.640365 | 42.6450 |
| 0.20R | -41.1224 | 0.590951 | 48.0674 |

## Caveats

- Nearest swing and structural stop use causal 3-bar pivots as a research approximation.
- FVG/OB groups use causal proximity evidence from the hybrid layer; they are not yet a retest-entry engine.
- Costs are sensitivity assumptions in R because the fixture has no bid/ask or commission.
- No variant changes the production CRT engine.
