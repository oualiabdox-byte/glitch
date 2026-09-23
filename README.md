# Private Forex ICT/SMC Research Bot

**Current architecture: Forex + cTrader Open API only.**

This repository is intentionally kept narrow so an automated agent, VPS deployment, or OpenClaw workspace cannot mistake historical broker/strategy implementations for the active system.

## Active components

- `strategy/` — causal ICT/SMC setup engine.
- `strategy/multi_timeframe.py` — closed-bar 1D bias, causal H1 structure, and M5 sweep/FVG entry research engine.
- `strategy/decision.py` — auditable SIGNAL/NO_TRADE decisions with reason codes and data cutoffs.
- `data/ctrader.py` — cTrader historical/live market-data boundary.
- `backtest/ctrader_runner.py` — local deterministic H1/H4 backtest runner.
- `backtest/data_quality.py` — fail-closed OHLC, timestamp and H4-axis checks.
- `execution/ctrader_adapter.py` — cTrader authentication, account state, reconciliation and explicitly gated order boundary.
- `execution/bot_main.py` — signal-only cTrader scan; order submission is disabled.
- `execution/ctrader_probe.py` — connectivity/account-state probe; no orders.
- `execution/demo_guard.py` — fail-closed guard for any future demo runner; live routing is not implemented.
- `tests/` — regression and look-ahead safeguards.
- `config/config.yaml` — Forex symbols, risk and execution defaults.
- `requirements.txt` — runtime/test dependencies.

## Local installation and cTrader connectivity

The repository is designed to be copied to a local computer and installed
without manually hunting for Python packages. Use Python 3.10 or newer:

```bash
git clone https://github.com/oualiabdox-byte/forex_bot.git
cd forex_bot
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in the cTrader Open API application and
account values supplied by cTrader. The adapter loads `.env` automatically;
shell environment variables still take precedence. Keep the safety setting
disabled while testing:

```bash
cp .env.example .env
# edit .env; keep CTRADER_ENV=demo and CTRADER_ALLOW_ORDERS=false
python -m execution.ctrader_probe
python -m pytest -q
```

The repository does **not** currently contain an autonomous order loop. The
adapter has low-level order methods, but `execution/bot_main.py` is signal-only
and never submits orders. Do not treat a successful probe or backtest as
authorization to trade. Any future demo runner must require
`CTRADER_ENV=demo`, `CTRADER_ALLOW_ORDERS=true`,
`CTRADER_DEMO_CONFIRM=I_UNDERSTAND_DEMO_TRADING`, and a positive
`CTRADER_MAX_ORDER_VOLUME_UNITS`. Live routing is intentionally not implemented
in this project.

After cTrader credentials are configured, the four-session MTF smoke test can
be run without enabling orders:

```bash
PYTHONPATH=. python -m backtest.multi_timeframe_smoke \
  --symbol EURUSD \
  --start 2026-09-17T00:00:00Z \
  --end 2026-09-23T00:00:00Z \
  --output results/mtf_four_session_smoke.json
```

The runner selects four weekday M5 sessions deterministically, aligns D1 and
H1 by completed-bar close time, and treats the result as an integration smoke
test—not as evidence of profitability.

The first conservative expansion keeps D1/H1, sweep buffer, FVG width, R:R,
and risk gates unchanged. It only permits a same-direction two-bar displacement
whose combined bodies reach `1.00 ATR`, and extends the first-retest window to
six completed M5 bars. The four-session comparison on the same EURUSD data
remained at 0 completed signals; this is a valid smoke-test observation, not a
profitability conclusion.

For detailed rejection diagnostics over a longer window, use the windowed
runner. It splits M5 downloads into fresh processes so cTrader's Twisted
reactor is not restarted in one process:

```bash
PYTHONPATH=. python -m backtest.multi_timeframe_smoke \
  --symbol EURUSD \
  --start 2026-08-24T00:00:00Z \
  --end 2026-09-23T00:00:00Z \
  --cache-dir /tmp/forex_bot_mtf_cache_30d \
  --output results/mtf_30d_diagnostics.json
```

The JSON output separates `D1_NEUTRAL_OR_UNCONFIRMED`, H1 state/mismatch,
M5 transition, FVG, history, retest, and other gate reasons instead of
collapsing them into `NO_SETUP`.

The revised D1 policy has two tiers. Confirmed break/reclaim bias remains
unchanged. An optional `BULLISH_WEAK` or `BEARISH_WEAK` location bias requires
two consecutive daily closes on the same side of equilibrium and a current
daily body in that direction; it is not a daily breakout. The extended runner
opts into this tier with `risk_multiplier=0.5`, while the core evaluator keeps
`allow_weak_daily=False` by default so callers must opt in explicitly.

The new strict model is available without replacing the legacy model:

```bash
PYTHONPATH=. python -m backtest.multi_timeframe_smoke \
  --model strict_ict_mtf \
  --symbol EURUSD \
  --start 2026-08-24T00:00:00Z \
  --end 2026-09-23T00:00:00Z \
  --cache-dir /tmp/forex_bot_mtf_cache_30d \
  --output results/strict_ict_mtf_30d.json
```

Its mandatory order is **D1 directional bias → H1 liquidity sweep and
discount/premium FVG POI → M5 POI sweep → close-confirmed BOS → objective
displacement → post-BOS CHoCH/MSS → Fib leg OTE → optional M5 FVG confluence →
entry on a later closed candle**. A BOS candle is never itself an entry. The
strict model defaults to `NO TRADE` for weak/neutral D1 and does not alter the
execution or broker layer.

H1 rejections are split into `H1_NO_LIQUIDITY_SWEEP`,
`H1_SWEEP_NO_FVG_AFTER`, `H1_FVG_WRONG_PREMIUM_DISCOUNT`,
`H1_POI_EXPIRED`, and `H1_PRICE_NOT_AT_POI`, so the strict diagnostic path no
longer collapses these into one generic POI rejection.

A separate, non-default research model `irl_erl_retest` is also available. It
first finds internal H1 liquidity (FVG/POI), then searches for external
liquidity above/below a later swing only to validate the range/Fibonacci. For
LONG, an H1 retest only needs to reach/touch 50%; an H1 close above or below
50% is not a gate. SHORT is the mirror image. Only after that validation does
it require M5 close-confirmed BOS → CHoCH (no M5 sweep gate and no M5 MSS) →
POI inside the BOS-to-CHoCH leg → POI retest. The candidate uses the BOS-forming
swing for SL and requires a confirmed new liquidity target at or above 1:1.5 R.
It does not modify `strict_ict_mtf`.

The 10-trading-day research command is:

```bash
PYTHONPATH=. python -m backtest.multi_timeframe_smoke \
  --model irl_erl_retest --symbol EURUSD \
  --start 2026-09-10T00:00:00Z --end 2026-09-24T00:00:00Z \
  --cache-dir /tmp/forex_bot_side_10d_cache \
  --output results/irl_erl_retest_10d.json
```

The implementation was informed by the operational descriptions in
[`smartmoneyconcepts`](https://github.com/joshyattridge/smart-money-concepts),
the vectorized `pyvsmc` package listing
([piwheels](https://www.piwheels.org/project/pyvsmc)), and the open-source
[Liquidity Swings & Sweeps](https://www.tradingview.com/script/sheX75nN-Liquidity-Swings-Sweeps/)
description. TradingKit was also reviewed; its public site is primarily a
MetaTrader tooling and risk-control hub rather than a source implementation of
ICT/SMC definitions, so only its risk-discipline emphasis was considered:
[TradingKit](https://tradingkit.net/). No external code was copied.

`ctrader-open-api`, `service-identity`, `python-dotenv`, Twisted, protobuf,
PyYAML, NumPy, and pytest are declared in `requirements.txt`. The probe only
authenticates and reads account/symbol state; it never submits an order when
`CTRADER_ALLOW_ORDERS=false`. Never commit `.env` or real credentials.

## Strategy decision path

The strict engine evaluates:

**4H confirmed structure → directional bias → directional liquidity target → 1H sweep → post-sweep MSS → displacement → fresh FVG retest → 4H premium/discount → allowed session → structural stop → minimum R:R → TRADE / NO TRADE**

FVG, order block and Fibonacci-cluster information is retained as auditable evidence. It does not create a trade by itself.

The research multi-timeframe engine uses a separate clock:

**Closed D1 candle bias → confirmed H1 BOS/CHoCH/MSS → H1 FVG → frozen H1 range → M5 internal-liquidity sweep/reclaim → M5 displacement → first FVG retest/rejection → next-M5-open entry.**

Every stage is closed-bar and causal. Daily bias becomes effective for the next session; centered pivots are available only after their right-side confirmation bars; and an M5 setup cannot enter on the same candle that creates its rejection. IRL/ERL and BB/mitigation/Unicorn are explicit, versioned research filters rather than standalone triggers. Their terminology is community-defined and their default filter is disabled until separately validated.

The optional `structure_entry` engine evaluates:

**4H permission → H1 IDM sweep → displacement MSS/BOS/CHOCH → continuation or shallow reclaim → directional 50% check → next-bar entry**

This path does not require an exact FVG or order-block touch. It is an explicitly defined research path, not a claim of profitability.

`strategy/risk_governor.py` is a separate fail-closed pre-trade gate. It checks quote freshness, spread, stop direction, broker volume economics, daily loss plus open worst-case risk, drawdown, position count and volume limits. A rejected candidate returns reason codes and cannot become an order.

The backtester consumes `Decision` objects at the strategy boundary instead of treating `None` as an unexplained rejection. Rejection counts are available after a run through `run.last_rejection_counts` and are intended for diagnostics, not as a performance metric.

Evaluator ablation flags are available for controlled one-condition-at-a-time experiments. ICT flags include `require_sweep`, `require_mss`, `require_displacement`, `require_fvg`, `require_order_block`, `require_session`, `require_premium_discount`, and `require_min_rr`; breakout flags include `require_target_pool` and `require_min_rr`. Defaults preserve the normal strategy behavior.

There is no arbitrary confidence score and no EMA/MACD/RSI indicator stack.

## Data and execution

cTrader Open API is the only broker/data boundary in this repository.

Development sequence:

**cTrader approval → local authentication → historical H1/H4 data → local backtest → out-of-sample/walk-forward validation → demo execution → only then deliberate live enablement**

The current code does not enable live order submission by default.

## Safety rules

- Strategy code does not contain broker-specific decisions.
- Order submission is explicitly gated by `CTRADER_ALLOW_ORDERS`.
- The selected cTrader environment is explicit through `CTRADER_ENV`.
- The H1 signal boundary is the H1 candle CLOSE; the signal candle is fully closed before strategy evaluation.
- H4 context includes only H4 candles whose CLOSE is at or before the H1 signal close.
- Entries are simulated on the next H1 bar.
- Historical cTrader trendbars are mid OHLC, not bid/ask tick data. The backtester therefore applies explicit spread/slippage/commission assumptions and reports the execution model.
- When SL and TP are both touched in one OHLC candle, the backtester records the trade as intrabar-ambiguous and applies the configured conservative SL-first policy.
- Backtest results are research measurements, not evidence of live profitability.

## Research discipline

Do not loosen filters merely to increase trade count. A higher trade count is not evidence of a stronger edge.

Changes to strategy logic must be tested as controlled A/B experiments on identical periods, with at minimum:

- trade count
- win rate
- profit factor
- expectancy in R
- net R
- maximum drawdown in R
- outcome distribution
- NO TRADE / rejection rates

Do not promote a parameter change based only on in-sample performance.

## Repository rule

Only the current Forex/cTrader implementation belongs here. Do not reintroduce obsolete broker integrations, cryptocurrency engines, alternative strategy branches, generated backtest reports, or unrelated agent-workspace files.


## Current implementation status

The repository is currently **signal-only**. `execution/bot_main.py` never submits orders.
Live execution is not part of the current validation path.

Before any deliberate execution enablement, the required sequence is:
1. cTrader application approval and local authentication.
2. Historical-data integrity checks.
3. Closed-bar/look-ahead test suite.
4. Long in-sample backtest with explicit transaction-cost assumptions.
5. Out-of-sample / walk-forward validation.
6. Demo execution and reconciliation.
7. Separate, explicit live authorization.

The cTrader adapter additionally requires an explicit live confirmation string and
an optional maximum order-volume cap when live order submission is eventually enabled.
