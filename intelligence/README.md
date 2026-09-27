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


## OpenRouter free routing

The repository does not pin a specific LLM model. Hindsight is configured at
runtime to use OpenRouter's free-model router:

    HINDSIGHT_API_LLM_PROVIDER=openrouter
    HINDSIGHT_API_LLM_MODEL=openrouter/free

openrouter/free is an OpenRouter router, not a specific model. OpenRouter
selects an available free model for each request. The API key is supplied only
through the runtime environment; it is never committed to the repository.

Docker Compose configuration:

    export OPENROUTER_API_KEY="sk-or-..."
    docker compose -f infra/hindsight/docker-compose.yml up -d

The Hindsight client in GLITCH remains provider-agnostic. Provider/model
selection belongs to the Hindsight service deployment, not the trading code.
