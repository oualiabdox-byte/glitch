# 14-day BOS + Liquidity Regime dynamic-stop test

BOS_AFTER_CHOCH plus causal Liquidity Regime v2 soft multiplier. Dynamic stops update only from prior completed M5 bars, avoiding same-bar lookahead. BE_1R moves stop to entry after prior-bar favorable movement reaches 1R; TRAIL_1R moves to +0.25R after 1R and +0.75R after 1.5R.

| Metric | Baseline | BE after 1R | Trail after 1R/1.5R | Conservative trail after 1.5R |
|---|---:|---:|---:|---:|
| Trades | 8.000000 | 9.000000 | 9.000000 | 9.000000 |
| Win rate % | 75.000000 | 55.555556 | 77.777778 | 77.777778 |
| PF | 4.050470 | 0.893232 | 2.067023 | 4.541209 |
| Total R raw | 3.741155 | -0.185380 | 1.293786 | 4.293786 |
| Total R weighted | 1.170479 | 0.125301 | 0.509339 | 1.358572 |
| Return % | 0.585563 | 0.062478 | 0.254776 | 0.680223 |
| Max DD % | 0.145757 | 0.140496 | 0.113185 | 0.113185 |
| Average weighted R | 0.146310 | 0.013922 | 0.056593 | 0.150952 |
