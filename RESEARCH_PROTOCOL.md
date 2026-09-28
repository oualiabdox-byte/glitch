# GLITCH — Research Protocol

## Baseline

The existing strategy is immutable baseline behavior.

Every experiment records:

- experiment ID
- dataset
- Git commit
- configuration
- setup IDs
- train/validation/test split
- metrics

## Causality

At timestamp T, only bars satisfying open_time + timeframe_duration <= T may be consumed.

## Same-set rule

Alternative target/entry models must evaluate the exact same setup IDs.

## Metrics

At minimum:

- N
- wins/losses/timeouts
- win rate
- profit factor
- expectancy
- net R
- average/median R
- maximum drawdown
- MFE/MAE
- duration

## No blind optimization

No rule is promoted because of one pair, one week, one exceptional trade, or a small sample.
