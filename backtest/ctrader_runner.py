"""Deterministic local cTrader H1/H4 backtest for the strict Forex ICT/SMC engine.

Signal time is the CLOSE of the H1 signal bar. The signal bar is therefore fully
closed before its data is used. Entry is on the next H1 bar. Historical cTrader
trendbars are OHLC/mid-price data, so this runner applies an explicit synthetic
spread/slippage/commission model and records OHLC ambiguity rather than
pretending OHLC can reveal intrabar order.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config.settings import load_config, pairs as configured_pairs
from data.ctrader import CTraderData
from strategy.ict_strategy import (
    evaluate_ict_2022,
    evaluate_breakout_retest,
    evaluate_structure_entry,
)
from strategy import risk, safety, timing


def dt(value) -> datetime:
    if isinstance(value, datetime):
        value = value.isoformat()
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def bar_close_time(bar, hours: int) -> datetime:
    return dt(bar["time"]) + timedelta(hours=hours)


def h4_until(h4, signal_close):
    ts = dt(signal_close)
    return [c for c in h4 if bar_close_time(c, 4) <= ts]


def load_or_download(feed, symbol, start, end, cache_dir):
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    key = f"{symbol}_{start:%Y%m%dT%H%M%SZ}_{end:%Y%m%dT%H%M%SZ}"
    path = cache / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    data = feed.download(symbol, start, end, periods=("h1", "h4"))
    path.write_text(json.dumps(data, indent=2))
    return data


def _pip_size(pair):
    return 0.01 if "JPY" in pair.upper() else 0.0001


def _execution_prices(mid, side, spread_price, slippage_price, exit=False):
    half = spread_price / 2.0
    slip = slippage_price
    if side == "LONG":
        return (mid + half + slip) if not exit else (mid - half - slip)
    return (mid - half - slip) if not exit else (mid + half + slip)


def _commission_r(pair, entry_price, stop_price, risk_amount, commission_per_lot):
    if commission_per_lot <= 0 or risk_amount <= 0:
        return 0.0
    distance = abs(entry_price - stop_price)
    pip = _pip_size(pair)
    if distance <= 0 or pip <= 0:
        return 0.0
    # Conservative sizing model for backtest costs: USD-quoted pairs use the
    # standard $10/pip per lot; JPY-quoted pairs convert the 1,000-JPY pip value.
    base_units = risk_amount / distance
    lots = base_units / 100000.0
    return (lots * commission_per_lot) / risk_amount


def run(
    symbol,
    start,
    end,
    cache_dir="data/ctrader_cache",
    entry_mode="ict_fvg",
    swing_length=3,
    max_trades_per_day=0,
    cooldown_minutes=0,
    max_drawdown_r=0.0,
    max_daily_loss_r=0.0,
    max_atr_spike=0.0,
    news_events=None,
    news_pause_before=45,
    news_pause_after=20,
    spread_pips=0.0,
    slippage_pips=0.0,
    commission_per_lot=0.0,
    risk_amount=50.0,
):
    feed = CTraderData()
    data = load_or_download(feed, symbol, start, end, cache_dir)
    h1, h4 = data["h1"], data["h4"]

    if len(h1) < 100 or len(h4) < 40:
        raise RuntimeError(f"Not enough cTrader data: H1={len(h1)}, H4={len(h4)}")

    pip = _pip_size(symbol)
    spread_price = spread_pips * pip
    slippage_price = slippage_pips * pip

    trades = []
    next_available_idx = 60
    last_entry_time = None
    equity_r = 0.0
    peak_equity_r = 0.0
    ambiguous_bars = 0

    evaluators = {
        "ict_fvg": evaluate_ict_2022,
        "breakout_retest": evaluate_breakout_retest,
        "structure_entry": evaluate_structure_entry,
    }
    if entry_mode not in evaluators:
        raise ValueError("entry_mode must be ict_fvg, breakout_retest, or structure_entry")
    evaluator = evaluators[entry_mode]

    # i is a CLOSED H1 signal bar. Its close is the information boundary.
    for i in range(60, len(h1) - 1):
        if i < next_available_idx:
            continue

        signal_close = bar_close_time(h1[i], 1)
        signal_time = signal_close.isoformat()
        session = timing.session_context(signal_close).session
        window = h1[: i + 1]

        if max_atr_spike > 0 and safety.abnormal_volatility(window, max_ratio=max_atr_spike):
            continue
        if safety.news_blocked(signal_close, symbol, news_events or [],
                               pause_before_minutes=news_pause_before,
                               pause_after_minutes=news_pause_after):
            continue
        if max_trades_per_day > 0 and risk.trades_on_day(trades, signal_time) >= max_trades_per_day:
            continue
        if not risk.cooldown_clear(last_entry_time, signal_time, cooldown_minutes):
            continue
        if not risk.daily_loss_guard(trades, signal_time, max_daily_loss_r):
            continue
        if not risk.drawdown_guard(equity_r, peak_equity_r, max_drawdown_r):
            continue

        h4_visible = h4_until(h4, signal_close)
        if len(h4_visible) < 30:
            continue

        setup = evaluator(
            window,
            h4_visible,
            symbol,
            session_context=session,
            swing_length=swing_length,
        )
        if not setup:
            continue

        entry_idx = i + 1
        side = setup["side"]
        mid_entry = h1[entry_idx]["open"]
        entry = _execution_prices(mid_entry, side, spread_price, slippage_price, exit=False)
        stop = setup["stop_price"]
        target = setup["tp_target"]

        if (side == "LONG" and entry <= stop) or (side == "SHORT" and entry >= stop):
            continue

        outcome = "OPEN"
        exit_price = h1[-1]["close"]
        exit_time = h1[-1]["time"]
        exit_idx = len(h1) - 1
        trade_ambiguous = False

        for j in range(entry_idx, len(h1)):
            candle = h1[j]
            # Historical data is mid OHLC. Apply the configured spread to the
            # executable side. If both protection levels are touched, ordering
            # is unknowable from OHLC; SL-first is explicit and conservative.
            if side == "LONG":
                executable_high = candle["high"] - spread_price / 2.0 - slippage_price
                executable_low = candle["low"] - spread_price / 2.0 - slippage_price
                sl = executable_low <= stop
                tp = executable_high >= target
            else:
                executable_high = candle["high"] + spread_price / 2.0 + slippage_price
                executable_low = candle["low"] + spread_price / 2.0 + slippage_price
                sl = executable_high >= stop
                tp = executable_low <= target

            if sl and tp:
                trade_ambiguous = True
                ambiguous_bars += 1
                outcome, exit_price = "SL", stop
                exit_time, exit_idx = candle["time"], j
                break
            if sl:
                outcome, exit_price = "SL", stop
                exit_time, exit_idx = candle["time"], j
                break
            if tp:
                outcome, exit_price = "TP", target
                exit_time, exit_idx = candle["time"], j
                break

        exit_exec = _execution_prices(exit_price, side, 0.0, 0.0, exit=True)
        risk_distance = abs(entry - stop)
        gross_r = (
            ((exit_exec - entry) / risk_distance if side == "LONG"
             else (entry - exit_exec) / risk_distance)
            if risk_distance else 0.0
        )
        commission_r = _commission_r(
            symbol, entry, stop, risk_amount, commission_per_lot
        )
        pnl_r = gross_r - commission_r

        next_available_idx = max(next_available_idx, exit_idx + 1)
        last_entry_time = signal_time
        equity_r += pnl_r
        peak_equity_r = max(peak_equity_r, equity_r)

        trades.append({
            "pair": symbol,
            "signal_close_utc": signal_time,
            "entry_time_utc": h1[entry_idx]["time"],
            "side": side,
            "entry_mid": mid_entry,
            "entry": entry,
            "stop": stop,
            "target": target,
            "outcome": outcome,
            "gross_r": gross_r,
            "commission_r": commission_r,
            "pnl_r": pnl_r,
            "rr": setup["rr"],
            "session": setup["session"],
            "exit_time_utc": exit_time,
            "intrabar_ambiguous": trade_ambiguous,
        })

    return trades, ambiguous_bars


def metrics(trades, ambiguous_bars=0):
    rs = [float(t["pnl_r"]) for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r < 0]
    equity = peak = drawdown = 0.0
    for r in rs:
        equity += r
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    gross_loss = abs(sum(losses))
    return {
        "trades": len(rs),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(rs) if rs else 0.0,
        "profit_factor": sum(wins) / gross_loss if gross_loss else 0.0,
        "expectancy_r": sum(rs) / len(rs) if rs else 0.0,
        "max_drawdown_r": drawdown,
        "net_r": sum(rs),
        "intrabar_ambiguous_trades": int(ambiguous_bars),
    }


def main():
    parser = argparse.ArgumentParser(description="Local cTrader Forex ICT/SMC backtest")
    parser.add_argument("--symbol")
    parser.add_argument(
        "entry-mode", choices=("ict_fvg", "breakout_retest", "structure_entry"), default="ict_fvg"
    )
    parser.add_argument("--all-pairs", action="store_true")
    parser.add_argument("--pairs", default="")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--cache-dir", default="data/ctrader_cache")
    parser.add_argument("--swing-length", type=int, default=3)
    parser.add_argument("--max-trades-per-day", type=int, default=0)
    parser.add_argument("--cooldown-minutes", type=int, default=0)
    parser.add_argument("--max-drawdown-r", type=float, default=0.0)
    parser.add_argument("--max-daily-loss-r", type=float, default=None)
    parser.add_argument("--max-atr-spike", type=float, default=0.0)
    parser.add_argument("--news-events-json", default="")
    parser.add_argument("--news-pause-before", type=int, default=45)
    parser.add_argument("--news-pause-after", type=int, default=20)
    parser.add_argument("--spread-pips", type=float, default=None)
    parser.add_argument("--slippage-pips", type=float, default=None)
    parser.add_argument("--commission-per-lot", type=float, default=None)
    parser.add_argument("--risk-amount", type=float, default=50.0)
    parser.add_argument("--json")
    args = parser.parse_args()

    cfg = load_config()
    if not args.symbol and not args.all_pairs and not args.pairs:
        parser.error("provide --symbol, --pairs or --all-pairs")

    configured = configured_pairs(cfg)
    pairs = (
        [args.symbol.upper()] if args.symbol
        else [p.strip().upper() for p in args.pairs.split(",") if p.strip()]
        if args.pairs
        else configured
    )
    if args.all_pairs:
        pairs = configured

    bt_cfg = cfg.get("backtest", {})
    if bt_cfg.get("look_ahead_guard") is not True or bt_cfg.get("require_closed_bars") is not True:
        raise RuntimeError("Backtest config must require closed bars and look-ahead protection")

    exec_cfg = cfg.get("execution", {})
    risk_cfg = cfg.get("risk", {})
    max_daily_loss_r = float(
        args.max_daily_loss_r
        if args.max_daily_loss_r is not None
        else risk_cfg.get("max_daily_loss_r", 0.0)
    )
    spread_pips = float(args.spread_pips if args.spread_pips is not None else exec_cfg.get("spread_pips", 1.5))
    slippage_pips = float(args.slippage_pips if args.slippage_pips is not None else exec_cfg.get("slippage_pips", 0.0))
    commission = float(args.commission_per_lot if args.commission_per_lot is not None else exec_cfg.get("commission_per_lot_round_turn", 0.0))

    news_events = safety.load_news_events(Path(args.news_events_json).read_text()) if args.news_events_json else []
    reports, all_trades, ambiguous = {}, [], 0

    for symbol in pairs:
        trades, amb = run(
            symbol, dt(args.start), dt(args.end),
            cache_dir=args.cache_dir,
            entry_mode=args.entry_mode,
            swing_length=args.swing_length,
            max_trades_per_day=args.max_trades_per_day,
            cooldown_minutes=args.cooldown_minutes,
            max_drawdown_r=args.max_drawdown_r,
            max_daily_loss_r=max_daily_loss_r,
            max_atr_spike=args.max_atr_spike,
            news_events=news_events,
            news_pause_before=args.news_pause_before,
            news_pause_after=args.news_pause_after,
            spread_pips=spread_pips,
            slippage_pips=slippage_pips,
            commission_per_lot=commission,
            risk_amount=args.risk_amount,
        )
        reports[symbol] = metrics(trades, amb)
        all_trades.extend(trades)
        ambiguous += amb

    report = {
        "symbols": pairs,
        "start": args.start,
        "end": args.end,
        "mode": "strict_ict_smc",
        "entry_mode": args.entry_mode,
        "data_source": "cTrader Open API historical H1/H4",
        "signal_boundary": "H1_CLOSE",
        "future_leak_guard": True,
        "closed_bar_only": True,
        "execution_model": {
            "source_prices": "cTrader historical mid OHLC",
            "spread_pips": spread_pips,
            "slippage_pips": slippage_pips,
            "commission_per_lot_round_turn": commission,
            "intrabar_policy": "SL_FIRST",
            "ambiguous_trades": ambiguous,
        },
        "risk_gates": {
            "max_trades_per_day": args.max_trades_per_day,
            "cooldown_minutes": args.cooldown_minutes,
            "max_drawdown_r": args.max_drawdown_r,
            "max_daily_loss_r": max_daily_loss_r,
            "max_atr_spike": args.max_atr_spike,
            "news_pause_before": args.news_pause_before,
            "news_pause_after": args.news_pause_after,
        },
        "pairs": reports,
        "aggregate": metrics(all_trades, ambiguous),
    }

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
