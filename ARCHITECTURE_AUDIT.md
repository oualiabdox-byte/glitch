# GLITCH — Architecture Audit

This branch implements the first approved repair tranche from the read-only audit.

## Scope

- Demo-only execution.
- No live routing.
- Preserve the canonical strategy baseline.
- Add causal/research infrastructure without silently changing signal semantics.

## Current critical controls

1. A centralized ClosedBarSnapshot provides a reusable causal boundary.
2. Demo orders require executable bid/ask data.
3. Signal age, spread, price drift, and execution-time RR are checked before submission.
4. Relative cTrader protection is calculated from the expected executable fill rather than the stale signal entry.
5. After fill, the system explicitly amends the position to the absolute intended SL/TP.
6. Protection-amendment failure halts Demo execution.
7. Broker symbol IDs can be normalized against internal pair names during reconciliation.
8. The outcome/OMS schema has fields for broker/deal/position identity and requested-vs-actual protection.

## Baseline policy

The current strategy and CURRENT_EXTERNAL target remain the baseline. Target and entry research must use identical setup IDs.

## Next tranche

- Complete outcome finalization on position closure.
- Add full OMS protected/closed/reconciled lifecycle semantics.
- Build causal liquidity/target candidate generation.
- Produce normalized setup/target/MFE/MAE CSV artifacts.
- Connect walk-forward validation to the experiment registry.
