# GLITCH — Demo Execution Safety

## Hard boundary

Live trading is disabled.

CTRADER_ENV must be demo; the cTrader adapter rejects live configuration.

## Pre-order checks

Before submission the Demo path measures:

- bid
- ask
- expected fill
- signal age
- spread
- price drift
- execution-time RR

A failed check produces explicit rejection codes.

## Protection

The intended stop and target are absolute strategy levels.

The initial market order uses distances from the expected executable fill because cTrader market orders require relative protection in this adapter.

After the fill, the adapter amends the position to the exact absolute intended stop and target.

If post-fill protection fails, the account is halted.

## Reconciliation

Broker order, position, and deal identifiers must be retained and normalized before comparing internal and broker state.
