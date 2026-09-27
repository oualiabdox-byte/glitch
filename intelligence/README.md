# GLITCH Trading Memory — Hindsight

Hindsight is an optional post-trade research/memory layer.

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

Retain only meaningful events: signal selections, order/execution events,
trade outcomes, reconciliation exceptions, and strategy/version changes.
Never retain credentials, tokens, account secrets, or raw market-data dumps.
