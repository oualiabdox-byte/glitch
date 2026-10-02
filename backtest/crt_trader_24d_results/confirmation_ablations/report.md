# CRT confirmation ablations — 24-day cTrader fixtures

> Research-only variants. The canonical CRT implementation was not changed.

| Variant | Trades | Win rate | Total R | Avg R | Profit factor | Max DD R |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 132 | 37.12% | -14.7224 | -0.1115 | 0.822622 | 26.9538 |
| confirm_2_closes | 84 | 40.48% | -14.1513 | -0.1685 | 0.716973 | 21.4118 |
| confirm_3_closes | 62 | 41.94% | -12.9302 | -0.2086 | 0.640827 | 14.0415 |
| sweep_depth_5pct | 90 | 37.78% | -5.0765 | -0.0564 | 0.909348 | 18.4046 |
| sweep_depth_10pct | 56 | 37.50% | -6.9639 | -0.1244 | 0.801031 | 16.6776 |
| body_ratio_0.30 | 114 | 36.84% | -12.6606 | -0.1111 | 0.824158 | 26.6511 |
| body_ratio_0.50 | 87 | 36.78% | -8.1847 | -0.0941 | 0.851187 | 22.7817 |
| displacement_0.50_atr | 28 | 50.00% | -5.8525 | -0.2090 | 0.581965 | 6.2734 |
| bos_after_reentry | 21 | 52.38% | -4.4793 | -0.2133 | 0.552067 | 6.5495 |
| sweep5_body30 | 80 | 36.25% | -5.4391 | -0.0680 | 0.89335 | 19.5262 |
| sweep5_body50 | 63 | 36.51% | -4.5895 | -0.0728 | 0.885262 | 17.7583 |
| sweep5_confirm2 | 59 | 40.68% | -10.8851 | -0.1845 | 0.688998 | 16.3438 |

## Interpretation

- `confirm_2_closes` and `confirm_3_closes` require consecutive closes back inside the swept level and delay entry to the last confirming close.
- `sweep_depth_*` measures the M5 sweep distance as a fraction of the parent CRT range.
- `body_ratio_*` filters the selected entry candle by body/range.
- `displacement_0.50_atr` waits for a two-bar move of at least 0.50 ATR in the target direction.
- `bos_after_reentry` waits for a close through a causally confirmed opposing pivot.

## Caveats

- Research-only ablation; no live or production strategy files were changed.
- Confirmation/displacement/BOS variants delay entry and therefore are not directly comparable to the original entry price without execution-cost modeling.
- OHLC data cannot resolve intrabar ordering; spread, slippage, commission, and news are absent.
- The BOS test uses causal 3-bar confirmed pivots and is an approximation of the original structure engine.
