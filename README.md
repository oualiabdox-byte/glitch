# Private Forex ICT/SMC Research Bot

**Current architecture: Forex + cTrader Open API only.**

This repository is intentionally kept narrow so an automated agent, VPS deployment, or OpenClaw workspace cannot mistake historical broker/strategy implementations for the active system.

## Active components

- `strategy/` — causal ICT/SMC setup engine.
- `data/ctrader.py` — cTrader historical/live market-data boundary.
- `backtest/ctrader_runner.py` — local deterministic H1/H4 backtest runner.
- `execution/ctrader_adapter.py` — cTrader authentication, account state, reconciliation and explicitly gated order boundary.
- `execution/bot_main.py` — signal-only cTrader scan; order submission is disabled.
- `execution/ctrader_probe.py` — connectivity/account-state probe; no orders.
- `tests/` — regression and look-ahead safeguards.
- `config/config.yaml` — Forex symbols, risk and execution defaults.
- `requirements.txt` — runtime/test dependencies.

## Strategy decision path

The strict engine evaluates:

**4H confirmed structure → directional bias → directional liquidity target → 1H sweep → post-sweep MSS → displacement → fresh FVG retest → 4H premium/discount → allowed session → structural stop → minimum R:R → TRADE / NO TRADE**

FVG, order block and Fibonacci-cluster information is retained as auditable evidence. It does not create a trade by itself.

There is no arbitrary confidence score and no EMA/MACD/RSI indicator stack.

## Data and execution

cTrader Open API is the only broker/data boundary in this repository.

Development sequence:

**cTrader approval → local authentication → historical H1/H4 data → local backtest → out-of-sample/walk-forward validation → demo execution → only then deliberate live enablement**

The current code does not enable live order submission by default.

## Safety rules

- Strategy code does not contain broker-specific decisions.
- Order submission is explicitly gated by `CTRADER_ALLOW_ORDERS`.
- The selected cTrader environment is explicit through `CTRADER_ENV`.
- Backtests use only higher-timeframe candles that were closed at the signal timestamp.
- Entries are simulated on the next H1 bar.
- When SL and TP are both touched in one OHLC candle, the backtester assumes SL first because tick ordering is unknown.
- Backtest results are research measurements, not evidence of live profitability.

## Research discipline

Do not loosen filters merely to increase trade count.

Changes to strategy logic must be tested as controlled A/B experiments on identical periods, with at minimum:

- trade count
- win rate
- profit factor
- expectancy in R
- net R
- maximum drawdown in R
- outcome distribution
- NO TRADE / rejection rates

Do not promote a parameter change based only on in-sample performance.

## Repository rule

Only the current Forex/cTrader implementation belongs here. Do not reintroduce obsolete broker integrations, cryptocurrency engines, alternative strategy branches, generated backtest reports, or unrelated agent-workspace files.
