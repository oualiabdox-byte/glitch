# Forex ICT/SMC Research Bot

Broker-independent ICT/SMC research, cTrader market data, backtesting, and execution.

## Architecture

- `strategy/`: causal, broker-independent signal logic.
- `data/ctrader.py`: cTrader historical/live market-data boundary.
- `backtest/ctrader_runner.py`: deterministic historical simulation using cTrader H1/H4 data.
- `execution/ctrader_adapter.py`: cTrader Open API authentication, account state, reconciliation, and future execution boundary.
- `tests/`: regression and look-ahead safeguards.

Legacy B2TRADER/MT5/Kraken integrations are not part of the target Forex runtime. The old B2TRADER code is retained temporarily only to preserve research history while the cTrader path is validated.

## Strategy

The hybrid engine uses independent entry models instead of requiring every SMC concept simultaneously:

1. Reversal: HTF bias + premium/discount + liquidity sweep/inducement.
2. Continuation: HTF bias + fresh FVG retest.
3. Expansion: directional displacement + confirmed post-event structure.

FVG, OB, OTE, breaker blocks, dominating candle, session and DOL remain context/confluence unless explicitly configured as hard constraints.

## cTrader

cTrader Open API supplies historical bars, live market data, account information, positions, orders and trading operations. The project uses the official Python SDK and keeps strategy logic separate from broker execution.

Development path:

`cTrader historical data -> backtest -> cTrader Demo -> validated live execution`

No live order submission is enabled by default.

## Validation

The backtester exposes only higher-timeframe candles that were fully closed at the signal timestamp, enters on the next H1 bar, and prevents overlapping positions. Results are expressed in R with expectancy, profit factor, win rate and drawdown.

Do not use backtest results as evidence for live profitability. Validate out-of-sample and walk-forward periods before enabling live orders.
