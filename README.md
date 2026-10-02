# forex_bot

A cTrader Open API forex research and demo-execution project using a deterministic **H1 location / M5 execution** strategy. The tested `bleach` strategy has replaced the old ICT/H4 strategy stack.

## Strategy model

```text
H1 confirmed structure
→ H1 dealing range and equilibrium
→ H1 discount/premium location
→ H1 FVG/POI
→ price returns to POI
→ M5 body-close BOS or CHOCH
→ protected-liquidity stop
→ untouched H1 swing target
```

The canonical confirmed-swing engine emits body-close `BOS`/`CHOCH` events, and the latest unambiguous event stream alone determines direction, protected swing, dealing range, and external liquidity. The sequence is H1 structure → H1 FVG location → temporally later POI touch → relevant M5 liquidity sweep → newest M5 same-direction BOS/CHOCH. Displacement is ATR-normalized evidence, not a mandatory gate; stale M5 breaks are never reused. The scanner records per-pair-and-variant setup lifecycle state and expires setups after the configured maximum age or when their premise changes. `strategy/engine.py` is the sole canonical strategy implementation; named variants are configurations of that engine.

## SVL alignment engine

The strategy also emits an auditable **Structure-Value-Liquidity (SVL)** context:

```text
Structure: HH/HL/LL/LH + BOS/CHOCH
Value:     OHLC-based Market Profile + VAH/POC/VAL + HVN/LVN
Liquidity: EQH/EQL and close-confirmed sweeps
Alignment: H1 context + latest M5 BOS/CHOCH direction
```

The native implementation in `strategy/svl.py` is dependency-free and works with cTrader trendbars. It consumes the same canonical structure snapshot; value and liquidity remain diagnostic layers. SVL evidence is included in scanner decisions. Strategy defaults come from `config/config.yaml` and can be overridden with the corresponding `CTRADER_*` environment settings, including `CTRADER_SWING_LENGTH`, `CTRADER_MIN_RR`, `CTRADER_STOP_BUFFER`, `CTRADER_ALLOW_WEAK_STRUCTURE`, `CTRADER_ALLOW_EQUILIBRIUM_OVERLAPPING_FVG`, `CTRADER_SETUP_MAX_AGE_HOURS`, `CTRADER_M5_CONFIRMATION_MODE`, and `CTRADER_SVL_*`.

## Install and configure cTrader

```bash
git clone https://github.com/oualiabdox-byte/forex_bot.git
cd forex_bot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

Set cTrader application credentials and the demo account ID in `.env`. Never commit `.env`; rotate credentials that have been exposed in chat or terminal output.

Probe cTrader connectivity without submitting orders:

```bash
PYTHONPATH=. python -m execution.ctrader_probe
```

## cTrader scanning

The scanner requests H1 and M5 trendbars, filters to candles whose scheduled close has passed, then rejects either timeframe if its latest completed bar remains behind the expected latest close beyond `risk.max_quote_age_seconds` (default `60`, overridable with `CTRADER_MAX_QUOTE_AGE_SECONDS`). The setting is a grace period after the expected bar close, not the raw age of an hourly candle. Freshness decisions are included in scan output. For matching pairs it evaluates every registered preset and prints one result per preset, labeled by its `variant`; other configured pairs use the existing YAML strategy through the same factory. EURUSD therefore emits two preset results and GBPUSD emits one. Only after every expected result has completed does the scanner emit a pair-level `signal_selection` record:

- A missing or failed variant makes selection `INCOMPLETE` and fails closed.
- Same-direction signals are ranked by explicit priority, an existing numeric signal quality score (if supplied), RR descending, existing H1 structure strength, then stable variant name and signal identity. Current priorities are tied. No short-window backtest is treated as historical validation confidence.
- Opposing directions produce an explicit `CONFLICT`; there is no arbitrary directional winner.
- Signal identity includes pair, closed-bar timestamp, and variant. Setup state remains isolated per pair/variant.
- All candidates are generated before the pair-level demo duplicate/order guard is applied.

The repeated runner records each variant and selection decision, and passes only the selected strategy signal directly to guarded demo execution. The order process validates execution/risk inputs and demo authorization; it does not run a second strategy or confluence layer:

```bash
PYTHONPATH=. python -m execution.bot_main --pair EURUSD
```

`NO_TRADE` includes reason codes and evidence. `SIGNAL_ONLY` includes:

```text
entry_price
stop_price
target_price
rr
evidence
```

The scanner is signal-only and never submits orders.

## Demo execution

Demo execution remains fail-closed and separate from scanning. It refuses non-demo environments and requires the explicit guard, confirmation string, positive volume, and volume cap.

```env
CTRADER_ENV=demo
CTRADER_ALLOW_ORDERS=true
CTRADER_DEMO_EXECUTE=true
CTRADER_DEMO_CONFIRM=I_UNDERSTAND_DEMO_TRADING
CTRADER_RUN_UNTIL_TRADE=true
CTRADER_POLL_SECONDS=300
CTRADER_ORDER_VOLUME_UNITS=1000
CTRADER_MAX_ORDER_VOLUME_UNITS=1000
CTRADER_PAIRS=EURUSD,GBPUSD,USDJPY,USDCHF,USDCAD,AUDUSD,NZDUSD
```

Run the guarded all-pairs demo runner:

```bash
PYTHONPATH=. python -m execution.demo_runner
```

Set `CTRADER_DEMO_EXECUTE=false` for signal-only operation. Live routing is not implemented. Verify broker minimum and step volume for every cTrader symbol before enabling demo submission.

## Position sizing and execution safety

The strategy does not size positions. The demo order boundary now validates cTrader symbol minimum, maximum, and step volume, and rounds down only so the broker request cannot exceed the requested risk.

The default remains fixed sizing for backward compatibility:

    CTRADER_SIZING_MODE=fixed
    CTRADER_ORDER_VOLUME_UNITS=1000
    CTRADER_MAX_ORDER_VOLUME_UNITS=1000

Risk sizing is opt-in and requires an explicit account-equity snapshot plus a cash conversion supplied in account currency:

    CTRADER_SIZING_MODE=risk
    CTRADER_ACCOUNT_EQUITY=10000
    CTRADER_RISK_PER_TRADE_PCT=0.005
    CTRADER_CASH_PER_UNIT_PRICE_MOVE=1.0
    CTRADER_MAX_ORDER_VOLUME_UNITS=1000

The cash conversion must be calculated for the account currency and symbol; the bot does not silently assume every pair is USD-quoted. If those values are missing, execution stops. Live order submission is disabled in the adapter; use demo only until a separately reviewed live execution boundary exists.

No additional strategy filters are enabled by default. This keeps the signal sample stable and puts overfitting control in the validation process rather than in an expanding list of gates.

## Overfitting control

`backtest/validation.py` provides chronological rolling train/test windows with an optional embargo. Use it to evaluate a small, predeclared parameter set on later data; do not select filters from the test window. The repository does not enable additional strategy gates by default just to improve one short sample.

## Validation

```bash
python3 -m pytest -q
```

The tests cover closed-bar causal structure, BOS/CHOCH behavior, H1 POI filtering, protected stops, stale-target rejection, H1/M5 data quality, cTrader safety gates, storage, and timing.

## Repository layout

- `strategy/engine.py` — sole canonical H1 location/M5 execution strategy.
- `strategy/variants.py` — named parameter presets and shared strategy factory.
- `strategy/selection.py` — deterministic pair-level signal selection and conflict handling.
- `strategy/structure.py` — confirmed swing labels and consumed BOS/CHOCH levels.
- `strategy/models.py` — candles and auditable decisions.
- `strategy/svl.py` — native Structure-Value-Liquidity analysis.
- `data/ctrader.py` — cTrader historical-data boundary.
- `execution/bot_main.py` — signal-only cTrader scanner.
- `execution/demo_guard.py` — fail-closed demo authorization.
- `execution/demo_runner.py` — repeated all-pairs demo scanner.
- `execution/demo_order.py` — one protected demo market order.
- `execution/storage.py` — local diagnostic persistence.
- `backtest/data_quality.py` — H1/M5 OHLC validation.

## Safety

This is research and demo software, not a profitability guarantee. Historical cTrader trendbars are OHLC data and cannot reveal intrabar ordering when both stop and target occur in one candle. Do not enable live trading. Never store access tokens, refresh tokens, client secrets, or account credentials in Git.

## Named strategy variants

The existing `strategy.engine.Strategy` logic is exposed through reproducible presets in `strategy/variants.py`:

- `eurusd_swing3_choch_or_bos` — swing length 3, `CHOCH_OR_BOS`
- `gbpusd_swing2_choch_only` — swing length 2, `CHOCH_ONLY`
- `eurusd_swing2_choch_or_bos` — swing length 2, `CHOCH_OR_BOS`

These presets do not replace the canonical strategy logic; live scans and historical backtests build the same engine using the causal swing and M5 confirmation settings shown above. The backtest reports independent per-variant results plus a separate pair-level run using the live selector. The demo-only runner consumes the selected output without strategy re-analysis and remains fail-closed. The open-data research runner is:

```bash
python3 backtest/original_variants_7d.py --days 7 --refresh
```

It writes `backtest/original_forex_variants_7d_results.csv`. Yahoo intraday candles are indicative research data, not executable bid/ask history, and the small seven-day sample is not a profitability guarantee.

## CRT/TBS research strategy

`backtest/crt_tbs_14d.py` is a separate, signal-only research implementation of the CRT + Turtle Body Soup rules from the supplied reference videos. It is intentionally not wired into demo execution. The rules are:

- completed 2-hour CRT range;
- next 2-hour candle sweeps one CRT boundary and closes back inside;
- on the following 2-hour bucket, find a lower-timeframe body-close TBS and close-back-through confirmation;
- require the two liquidity reference points to be 2–6 M5 candles apart;
- stop beyond the sweep, take 50% at CRT equilibrium, move the remainder to breakeven, and target the opposite CRT boundary.

The default universe is exactly three forex pairs—`EURUSD`, `GBPUSD`, and `USDJPY`—plus `GOLD` using Yahoo `GC=F` as a public gold-futures proxy. Run the 14-day research test with:

```bash
python3 backtest/crt_tbs_14d.py --days 14
```

Outputs are written to `backtest/crt_tbs_14d_results/` (`report.md`, `summary.json`, and `trades.csv`). This is a small-sample research result: Yahoo OHLC is indicative, not broker-executable, and the backtest excludes spread, slippage, commission, financing, and contract-specific sizing. Do not use the result as a profitability guarantee or connect this strategy to live execution without further validation.

## Adaptive allocation framework

`allocation/adaptive_portfolio.py` provides a research-only allocation layer for competing signals. It does not create signals and it is not connected to live or demo order submission. The default policy is:

- **0.25% of equity per accepted trade**;
- **1.00% maximum total open risk**;
- **0.50% maximum risk per currency cluster**;
- **0.50% maximum risk per correlated cluster**;
- maximum four open positions;
- reject, rather than silently resize, a signal that violates a risk budget;
- rank candidates by quality, prior expectancy, and a conservative small-sample penalty.

The allocator reduces concentration in related instruments using two independent backstops:

1. semantic currency clusters, such as `EURUSD`/`GBPUSD`/`AUDUSD`/`NZDUSD` and `USDJPY`/`USDCHF`/`USDCAD`;
2. a rolling-return correlation matrix estimated strictly from data available before the allocation timestamp, with a default high-correlation threshold of `0.70`.

The intended workflow is to generate all valid signals first, rank them, apply the allocation decision once per timestamp, then pass only accepted signals to a separately guarded execution layer. Correlations, historical expectancy, and quality scores must be point-in-time values; full-sample estimates are not valid for production evaluation.

Run the focused allocation tests with:

```bash
python3 -m pytest -q tests/test_adaptive_portfolio.py tests/test_volume_cycle_allocator.py
```
