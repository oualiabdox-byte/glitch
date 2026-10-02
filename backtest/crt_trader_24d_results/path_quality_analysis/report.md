# CRT entry-to-target path quality (24 days)

> Descriptive analysis only: the 132 accepted trades and their original exits were not changed.

## Outcome split

| Path outcome | Trades |
|---|---:|
| STOP_BEFORE_EQ | 83 |
| EQ_THEN_BE | 36 |
| EQ_THEN_TARGET | 13 |

## By volatility regime

| Regime | Trades | Outcome counts |
|---|---:|---|
| RANGE_CONTRACTION | 68 | `{"EQ_THEN_BE": 18, "EQ_THEN_TARGET": 7, "STOP_BEFORE_EQ": 43}` |
| RANGE_EXPANSION | 54 | `{"EQ_THEN_BE": 12, "EQ_THEN_TARGET": 6, "STOP_BEFORE_EQ": 36}` |
| TRANSITION | 10 | `{"EQ_THEN_BE": 6, "STOP_BEFORE_EQ": 4}` |

## Feature medians by path outcome

| Outcome | Trades | Target R | Eq R | Obstacles | First obstacle ATR | 3-bar displacement/R | MFE R |
|---|---:|---:|---:|---:|---:|---:|---:|
| EQ_THEN_BE | 36 | 4.1981 | 0.8557 | 1.0 | 1.8446 | 0.3139 | 1.3606 |
| EQ_THEN_TARGET | 13 | 4.5083 | 1.3283 | 1.0 | 2.069 | 1.3319 | 3.1077 |
| STOP_BEFORE_EQ | 83 | 7.1747 | 3.7407 | 0.0 | 1.1429 | -0.3717 | 0.0 |

## Confirmation rates by path outcome

| Outcome | HTF alignment | BOS after re-entry | Equilibrium reached |
|---|---:|---:|---:|
| STOP_BEFORE_EQ | 16.87% | 36.14% | 0.00% |
| EQ_THEN_BE | 50.00% | 80.56% | 100.00% |
| EQ_THEN_TARGET | 46.15% | 92.31% | 100.00% |

## Displacement bands

| 3-bar aligned body / initial risk | Trades | Eq reached | Target reached | Total R |
|---|---:|---:|---:|---:|
| (-999.0, -0.25] | 52 | 11.54% | 1.92% | -44.8074 |
| (-0.25, 0.0] | 12 | 50.00% | 0.00% | -3.0848 |
| (0.0, 0.5] | 23 | 47.83% | 4.35% | 5.1274 |
| (0.5, 1.0] | 17 | 52.94% | 29.41% | 4.7781 |
| (1.0, 999.0] | 28 | 60.71% | 25.00% | 23.2643 |

## Caveat

The obstacle/FVG/structure metrics are diagnostic approximations aligned with the original engine's concepts. They are not entry rules and were not used to select or remove trades.
