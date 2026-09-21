# Forex ICT/SMC Research Bot

Broker-independent ICT/SMC research, cTrader market data, backtesting, and execution.

## Architecture

- `strategy/`: causal, broker-independent signal logic.
- `data/ctrader.py`: cTrader historical/live market-data boundary.
- `backtest/ctrader_runner.py`: deterministic historical simulation using cTrader H1/H4 data.
- `execution/ctrader_adapter.py`: cTrader Open API authentication, account state, reconciliation, and future execution boundary.
- `tests/`: regression and look-ahead safeguards.

The repository contains only the cTrader Forex runtime. Legacy B2TRADER, MT5, Kraken, and Exness runtime files have been removed from this branch.

## Strategy

The hybrid engine uses independent entry models instead of requiring every SMC concept simultaneously:

1. Reversal: HTF bias + premium/discount + confirmed liquidity sweep + causal ABC structure. The ABC layer replaces the previously permissive sweep-only reversal trigger and uses the FOMO LL/HH for structural invalidation. Hybrid sweep detection now uses confirmed swing liquidity by default; legacy rolling-window sweep detection remains available for A/B control.
2. Continuation: HTF bias + fresh FVG retest + price-action trigger candle. LONG requires the retest candle to close above the previous candle high; SHORT requires a close below the previous candle low. This uses no RSI/EMA filter. The backtester exposes --continuation-mode price_action|legacy and --sweep-mode structure|legacy for controlled A/B testing.
3. Expansion: directional displacement + confirmed post-event structure.

No new RSI/EMA/MACD-style indicator stack is introduced. The first TradingKit/DaviddTech mix is a structural replacement inside the existing ICT/SMC engine, not a separate strategy.

FVG, OB, OTE, breaker blocks, dominating candle, session and DOL remain context/confluence unless explicitly configured as hard constraints.

## cTrader

cTrader Open API supplies historical bars, live market data, account information, positions, orders and trading operations. The project uses the official Python SDK and keeps strategy logic separate from broker execution.

Development path:

`cTrader historical data -> backtest -> cTrader Demo or Live execution`

Execution is explicitly controlled by `CTRADER_ENV` (`demo` or `live`) and `CTRADER_ALLOW_ORDERS=true`. Keep the environment set to the account you intentionally want to trade.

## Validation

The backtester exposes only higher-timeframe candles that were fully closed at the signal timestamp, enters on the next H1 bar, and prevents overlapping positions. Results are expressed in R with expectancy, profit factor, win rate and drawdown.

For controlled reversal A/B testing, backtest/ctrader_runner.py exposes --reversal-mode abc|legacy. The default is abc; use legacy only as the research control so both variants can be run on the same cTrader dataset.

Do not use backtest results as evidence for live profitability. Validate out-of-sample and walk-forward periods before enabling live orders.
