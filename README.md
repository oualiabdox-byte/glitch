# Private Forex ICT/SMC Research Bot

**Current architecture: Forex + cTrader Open API only.**

This repository is intentionally kept narrow so an automated agent, VPS deployment, or OpenClaw workspace cannot mistake historical broker/strategy implementations for the active system.

## Active components

- `strategy/` — causal ICT/SMC setup engine.
- `strategy/decision.py` — auditable SIGNAL/NO_TRADE decisions with reason codes and data cutoffs.
- `data/ctrader.py` — cTrader historical/live market-data boundary.
- `backtest/ctrader_runner.py` — local deterministic H1/H4 backtest runner.
- `backtest/data_quality.py` — fail-closed OHLC, timestamp and H4-axis checks.
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

The optional `structure_entry` engine evaluates:

**4H permission → H1 IDM sweep → displacement MSS/BOS/CHOCH → continuation or shallow reclaim → directional 50% check → next-bar entry**

This path does not require an exact FVG or order-block touch. It is an explicitly defined research path, not a claim of profitability.

`strategy/risk_governor.py` is a separate fail-closed pre-trade gate. It checks quote freshness, spread, stop direction, broker volume economics, daily loss plus open worst-case risk, drawdown, position count and volume limits. A rejected candidate returns reason codes and cannot become an order.

The backtester consumes `Decision` objects at the strategy boundary instead of treating `None` as an unexplained rejection. Rejection counts are available after a run through `run.last_rejection_counts` and are intended for diagnostics, not as a performance metric.

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
- The H1 signal boundary is the H1 candle CLOSE; the signal candle is fully closed before strategy evaluation.
- H4 context includes only H4 candles whose CLOSE is at or before the H1 signal close.
- Entries are simulated on the next H1 bar.
- Historical cTrader trendbars are mid OHLC, not bid/ask tick data. The backtester therefore applies explicit spread/slippage/commission assumptions and reports the execution model.
- When SL and TP are both touched in one OHLC candle, the backtester records the trade as intrabar-ambiguous and applies the configured conservative SL-first policy.
- Backtest results are research measurements, not evidence of live profitability.

## Research discipline

Do not loosen filters merely to increase trade count. A higher trade count is not evidence of a stronger edge.

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


## Current implementation status

The repository is currently **signal-only**. `execution/bot_main.py` never submits orders.
Live execution is not part of the current validation path.

Before any deliberate execution enablement, the required sequence is:
1. cTrader application approval and local authentication.
2. Historical-data integrity checks.
3. Closed-bar/look-ahead test suite.
4. Long in-sample backtest with explicit transaction-cost assumptions.
5. Out-of-sample / walk-forward validation.
6. Demo execution and reconciliation.
7. Separate, explicit live authorization.

The cTrader adapter additionally requires an explicit live confirmation string and
an optional maximum order-volume cap when live order submission is eventually enabled.
