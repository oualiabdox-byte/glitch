# Forex ICT/SMC Research Bot

Broker-independent ICT/SMC research and backtesting project.

## Architecture

- `strategy/`: causal, broker-independent signal logic.
- `data/`: market-data adapters.
- `backtest/`: deterministic historical simulation.
- `execution/`: broker integration, isolated from strategy logic.
- `tests/`: regression and look-ahead safeguards.

The hybrid engine uses independent entry models instead of requiring every
SMC concept simultaneously:

1. Reversal: HTF bias + premium/discount + liquidity sweep/inducement.
2. Continuation: HTF bias + fresh FVG retest.
3. Expansion: directional displacement + confirmed post-event structure.

FVG, OB, OTE, breaker blocks, dominating candle, session and DOL remain
context/confluence unless explicitly configured as hard constraints.

## Validation

The backtester uses only higher-timeframe candles available at the signal
timestamp, enters on the next bar, and prevents overlapping positions.
Results are expressed in R with expectancy, profit factor and drawdown.

No live trading is enabled by default. Validate with out-of-sample and
walk-forward periods before deployment.
