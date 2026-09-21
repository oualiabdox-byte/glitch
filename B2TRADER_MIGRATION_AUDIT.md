# B2TRADER migration audit

Branch: `b2trader-migration`  
Base: `main`

## Current repository findings

The existing project is already Forex-focused, but the data/execution layers are inconsistent:

- `strategy/` contains the ICT 2022 and ICT Hybrid implementations and is independent of broker execution.
- `backtest/exness_runner.py` directly imports `data.exness_ticks.ExnessTickData`.
- `data/exness_ticks.py` downloads Exness public tick archives and builds 5m/1H/4H candles.
- `data/exness_mt5.py` is an MT5 historical-data adapter.
- `forex_data.py` is still an MT5/MQL5-oriented stub and currently returns no candles.
- `execution/kraken_adapter.py` is a crypto-only adapter with live submission blocked.
- `execution/bot_main.py` still imports `forex_data.fetch_ohlc` and therefore is not connected to a real Forex provider.
- `.github/workflows/ict-hybrid-backtest.yml` still invokes `backtest.exness_runner`.

## Strategy preservation

No file under `strategy/` is modified by this migration branch.

The following existing strategy entry points were inspected:

- `strategy/ict_strategy.py`
- `strategy/ict_hybrid.py`
- `strategy/risk.py`

The new B2TRADER layer consumes their existing candle interface and does not change their parameters or decision logic.

## B2TRADER facts verified from official documentation

- OpenAPI page exposes raw specifications for K-Line, CFD order, CFD stop order, market, position, and token APIs.
- Guest market data requires no access token.
- Guest markets: `GET /frontoffice/api/v5/guest/markets`.
- Guest market details: `GET /frontoffice/api/v5/guest/markets/{marketId}`.
- Historical candles: `GET /marketdata/api/v4/guest/instruments/{marketSymbol}/history`.
- Guest historical windows: 1/5/15/30m up to 30 days; 1/4/12h up to 365 days; 1d/1w/1mo up to 5 years.
- Authenticated access uses an offline token exchanged through `POST /frontoffice/api/v4/access-token`; access tokens last 60 minutes.
- CFD order submission is `POST /frontoffice/api/cfd/v4/orders`, with `requestedLotAmount`, leverage, and optional stopLoss/takeProfit fields.
- No live order is submitted by this branch.

## Important unresolved item

B2TRADER API paths are relative to a broker-specific `{host}`. This branch therefore requires `B2TRADER_BASE_URL` to be supplied before an actual data download can be run.

The history response is normalized defensively, but the exact tenant response should be validated against the real B2TRADER host before relying on a production backtest.

## Intentionally not done

- No strategy optimization.
- No strategy changes.
- No live trading.
- No deletion of MT5/Exness/Kraken code yet.
- No claim that B2TRADER data has been successfully downloaded until a real host is configured.
