# GLITCH Trading Memory — Hindsight

Hindsight is an optional post-trade and backtest research/memory layer.

Architecture:

    Strategy -> Risk -> OMS/Execution -> Broker
                         |
                         +-- local EventStore
                                  |
                                  v
                           Hindsight (optional)
                                  |
                           Recall / Reflect

Hindsight is not in the execution decision path. It cannot approve, reject,
size, submit, cancel, or modify orders.

## Configuration

Self-hosted Hindsight can expose its API on http://localhost:8888.

    GLITCH_HINDSIGHT_ENABLED=true
    HINDSIGHT_API_URL=http://localhost:8888
    HINDSIGHT_BANK_ID=glitch-trading

If authentication is enabled:

    HINDSIGHT_API_KEY=...

The trading system remains functional when Hindsight is disabled or unavailable.

## Runtime events

Retain only meaningful events: signal selections, order/execution events,
trade outcomes, reconciliation exceptions, and strategy/version changes.
Never retain credentials, tokens, account secrets, or raw market-data dumps.

## Backtest research

Historical backtest CSVs can be converted into deterministic Markdown reports:

    PYTHONPATH=. python scripts/backtest_report.py path/to/results.csv --hindsight

The report is written to reports/backtests/. When Hindsight is enabled, only
the structured report summary is retained as a BACKTEST_REPORT memory. Raw
market data is not sent to Hindsight.

Workflow:

    Backtest data
        |
        v
    Deterministic report
        |
        +--> Hindsight research memory
        |
        +--> GitHub Markdown report
                    |
                    v
                  Manus

Reports are historical evidence. They must not authorize orders, change risk,
or mutate the strategy automatically.
