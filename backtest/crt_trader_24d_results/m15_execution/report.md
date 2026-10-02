# CRT M15 execution comparison — 24 days

> M15 is a separate execution backtest. The original M5 CRT is unchanged.

| Mode | Trades | Win rate | Total R | PF | Max DD R | Median min | <=15m | >60m | Eq reached |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| m5_current | 132 | 37.12% | -14.7224 | 0.822622 | 27.0228 | 20.0 | 49.24% | 18.94% | 37.12% |
| m15 | 1 | 100.00% | 0.5418 | inf | 0.0000 | 30.0 | 0.0% | 0.0% | 100.0% |
| m15_gap12 | 1 | 100.00% | 0.5418 | inf | 0.0000 | 30.0 | 0.0% | 0.0% | 100.0% |
| m15_4h | 79 | 44.30% | 12.9133 | 1.293483 | 10.8353 | 60.0 | 21.52% | 39.24% | 44.3% |
| m15_4h_gap12 | 106 | 41.51% | 0.7763 | 1.01252 | 16.2484 | 60.0 | 19.81% | 38.68% | 41.51% |
| m15_4h_m5_confirm | 79 | 44.30% | 12.9133 | 1.293483 | 10.8353 | 60.0 | 21.52% | 39.24% | 44.3% |
| m15_4h_gap12_m5_confirm | 106 | 41.51% | 0.7763 | 1.01252 | 16.2484 | 60.0 | 19.81% | 38.68% | 41.51% |

## Cost sensitivity

| Mode | Cost | Total R | PF |
|---|---:|---:|---:|
| m5_current | 0.05R | -21.3224 | 0.755596 |
| m5_current | 0.10R | -27.9224 | 0.695129 |
| m15 | 0.05R | 0.4918 | inf |
| m15 | 0.10R | 0.4418 | inf |
| m15_gap12 | 0.05R | 0.4918 | inf |
| m15_gap12 | 0.10R | 0.4418 | inf |
| m15_4h | 0.05R | 8.9633 | 1.193951 |
| m15_4h | 0.10R | 5.0133 | 1.103443 |
| m15_4h_gap12 | 0.05R | -4.5237 | 0.930568 |
| m15_4h_gap12 | 0.10R | -9.8237 | 0.856421 |
| m15_4h_m5_confirm | 0.05R | 8.9633 | 1.193951 |
| m15_4h_m5_confirm | 0.10R | 5.0133 | 1.103443 |
| m15_4h_gap12_m5_confirm | 0.05R | -4.5237 | 0.930568 |
| m15_4h_gap12_m5_confirm | 0.10R | -9.8237 | 0.856421 |

## Caveats

- M15 aggregates the repository M5 OHLC into 15-minute bars; intrabar ordering remains unknown.
- The Hybrid requires an M5 close inside the M15 re-entry bar; it is not a full delayed M5-to-M15 retest model.
- No spread, slippage, commission, or news costs are in the fixtures.
