# GLITCH — Demo Operations

This repository is Demo-only.

Required execution authorization:

- CTRADER_ENV=demo
- CTRADER_ALLOW_ORDERS=true
- CTRADER_DEMO_CONFIRM=I_UNDERSTAND_DEMO_TRADING
- CTRADER_MAX_ORDER_VOLUME_UNITS > 0

Run dry-run first.

A reconciliation mismatch, unknown execution state, or post-fill protection failure must halt further Demo orders.

Live routing is not an operational mode.
