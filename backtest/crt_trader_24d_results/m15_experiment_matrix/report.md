# Separate M15 CRT experiment matrix — 24-day sample

> This is a research-only analysis. It does not modify or import the installed production engine.

## Scope

- Frozen input: `m15_execution/m15_4h_trades.csv` (79 trades).
- Body thresholds: `0.30, 0.40, 0.50, 0.60, 0.70`.
- Minimum stop thresholds: `0.50, 0.60, 0.75, 0.90, 1.00 ATR`.
- Every result is split into `ALL`, `LONG`, and `SHORT`.
- The interaction table is descriptive; no automatic best-combination selection was performed.

## Loss anatomy

| Group | N | Body median | Stop ATR median | Sweep ATR median | Re-entry ATR median | Eq distance ATR median | Duration median (min) |
|---|---:|---:|---:|---:|---:|---:|---:|
| LOSS | 44 | 0.5845 | 0.6729 | 0.3454 | 0.1796 | 2.1883 | 37.5 |
| WIN | 35 | 0.6735 | 0.9037 | 0.4742 | 0.2922 | 1.0947 | 90.0 |

### Directional loss anatomy

| Direction | Losses | Winners | Loss body median | Loss stop median | Loss duration median (min) |
|---|---:|---:|---:|---:|---:|
| LONG | 23 | 11 | 0.6167 | 0.7133 | 30.0 |
| SHORT | 21 | 24 | 0.5102 | 0.6339 | 45.0 |

## Body robustness — ALL direction

| Body >= | N | Win rate | Total R | PF | Max DD R |
|---:|---:|---:|---:|---:|---:|
| 0.30 | 68 | 50.00% | 20.3782 | 1.599359 | 6.8353 |
| 0.40 | 62 | 51.61% | 18.8928 | 1.629759 | 5.2546 |
| 0.50 | 53 | 49.06% | 12.7561 | 1.472449 | 5.6586 |
| 0.60 | 42 | 50.00% | 3.9688 | 1.188989 | 7.3797 |
| 0.70 | 27 | 59.26% | 10.3145 | 1.93768 | 3.0000 |

## Minimum-stop robustness — ALL direction

| Stop >= ATR | N | Win rate | Total R | PF | Max DD R |
|---:|---:|---:|---:|---:|---:|
| 0.50 | 61 | 52.46% | 21.7005 | 1.748291 | 7.3686 |
| 0.60 | 56 | 51.79% | 12.0543 | 1.446457 | 5.9273 |
| 0.75 | 41 | 58.54% | 11.2633 | 1.662549 | 4.2546 |
| 0.90 | 30 | 60.00% | 5.5082 | 1.45902 | 4.0000 |
| 1.00 | 23 | 65.22% | 8.8715 | 2.108936 | 3.0000 |

## Interpretation guardrails

- The matrix does not freeze a new threshold and does not change production.
- A stable area must preserve results across nearby thresholds and both directions; a single peak is not evidence.
- Displacement was not available in the input CSV, so no displacement conclusion is claimed.
- The current sample is one 24-day window and needs chronological OOS validation before any future engine change.
