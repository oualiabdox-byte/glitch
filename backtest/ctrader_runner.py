"""cTrader historical backtest runner for the ICT/SMC strategy.

The strategy remains broker-independent. cTrader supplies the historical H1/H4
bars, while the existing causal strategy produces the signal. No live orders
are submitted by this module.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
from datetime import datetime, timezone
from pathlib import Path

from data.ctrader import CTraderData
from strategy.ict_strategy import evaluate_ict_2022
from strategy.ict_hybrid import evaluate_ict_hybrid


def dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _h4_until(h4, timestamp):
    ts = dt(timestamp).timestamp()
    return [c for c in h4 if dt(c["time"]).timestamp() + 4 * 3600 <= ts]


def _load_or_download(feed, symbol, start, end, cache_dir):
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    key = f"{symbol}_{start:%Y%m%dT%H%M%SZ}_{end:%Y%m%dT%H%M%SZ}"
    path = cache / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    data = feed.download(symbol, start, end, periods=("h1", "h4"))
    path.write_text(json.dumps(data, indent=2))
    return data


def run(symbol, start, end, mode="hybrid", cache_dir="data/ctrader_cache",
        enable_breaker=True, enable_ote=True, enable_mitigation=True,
        min_confluence=0, reversal_mode="abc", continuation_mode="price_action", sweep_mode="structure"):
    feed = CTraderData()
    data = _load_or_download(feed, symbol, start, end, cache_dir)
    h1, h4 = data["h1"], data["h4"]

    if len(h1) < 100 or len(h4) < 40:
        raise RuntimeError(f"Not enough cTrader data: H1={len(h1)}, H4={len(h4)}")

    fn = evaluate_ict_2022 if mode == "strict" else evaluate_ict_hybrid
    trades = []
    next_available_idx = 60

    for i in range(60, len(h1) - 1):
        if i < next_available_idx:
            continue

        signal_time = h1[i]["time"]
        h4_visible = _h4_until(h4, signal_time)
        if len(h4_visible) < 30:
            continue

        if mode == "strict":
            setup = fn(h1[:i + 1], h4_visible, symbol, session_context="london")
        else:
            setup = fn(
                h1[:i + 1], h4_visible, symbol,
                enable_breaker=enable_breaker,
                enable_ote=enable_ote,
                enable_mitigation=enable_mitigation,
                min_confluence=min_confluence,
                reversal_confirmation=reversal_mode,
                continuation_confirmation=continuation_mode,
                sweep_confirmation=sweep_mode,
            )

        if not setup:
            continue

        entry_idx = i + 1
        entry = h1[entry_idx]["open"]
        side = setup["side"]
        stop = setup["stop_price"]
        target = setup["tp_target"]

        if (side == "LONG" and entry <= stop) or (side == "SHORT" and entry >= stop):
            continue

        outcome = "OPEN"
        exit_price = h1[-1]["close"]
        exit_time = h1[-1]["time"]
        exit_idx = len(h1) - 1

        for j in range(entry_idx, len(h1)):
            candle = h1[j]
            sl = candle["low"] <= stop if side == "LONG" else candle["high"] >= stop
            tp = candle["high"] >= target if side == "LONG" else candle["low"] <= target

            # Conservative OHLC rule: if both are touched in one candle,
            # count SL first because tick ordering is unknown.
            if sl:
                outcome, exit_price, exit_time, exit_idx = "SL", stop, candle["time"], j
                break
            if tp:
                outcome, exit_price, exit_time, exit_idx = "TP", target, candle["time"], j
                break

        next_available_idx = max(next_available_idx, exit_idx + 1)
        risk = abs(entry - stop)
        pnl_r = (
            ((exit_price - entry) / risk if side == "LONG" else (entry - exit_price) / risk)
            if risk else 0.0
        )

        trades.append({
            "pair": symbol,
            "signal_time_utc": signal_time,
            "entry_time_utc": h1[entry_idx]["time"],
            "side": side,
            "entry": entry,
            "stop": stop,
            "tp1": target,
            "tp2": target,
            "outcome": outcome,
            "pnl_r": pnl_r,
            "rr": setup["rr"],
            "entry_trigger": setup.get("entry_trigger", "STRICT"),
            "event_type": setup.get("event_type"),
            "entry_model": setup.get("entry_model"),
            "reversal_confirmation": setup.get("reversal_confirmation"),
            "abc_confirmed": setup.get("abc_confirmed", False),
            "abc_pattern": setup.get("abc_pattern"),
            "abc_break_level": setup.get("abc_break_level"),
            "abc_fomo_extreme": setup.get("abc_fomo_extreme"),
            "pullback_trigger_confirmed": setup.get("pullback_trigger_confirmed", False),
            "continuation_confirmation": setup.get("continuation_confirmation"),
            "sweep_confirmation": setup.get("sweep_confirmation"),
            "confluence_score": setup.get("confluence_score"),
            "confluence_max": setup.get("confluence_max"),
            "premium_discount_zone": setup.get("premium_discount_zone"),
            "session_valid": setup.get("session_valid"),
            "dol_available": setup.get("dol_available"),
            "exit_time_utc": exit_time,
        })

    return trades


def metrics(trades):
    rs = [float(t["pnl_r"]) for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r < 0]
    equity = peak = drawdown = 0.0

    for r in rs:
        equity += r
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)

    gross_loss = abs(sum(losses))
    triggers = {}
    for trade in trades:
        key = trade.get("entry_trigger") or "UNKNOWN"
        triggers[key] = triggers.get(key, 0) + 1

    return {
        "trades": len(rs),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(rs) if rs else 0.0,
        "profit_factor": sum(wins) / gross_loss if gross_loss else 0.0,
        "expectancy_r": sum(rs) / len(rs) if rs else 0.0,
        "max_drawdown_r": drawdown,
        "net_r": sum(rs),
        "entry_triggers": triggers,
        "abc_reversals": sum(1 for t in trades if t.get("abc_confirmed")),
        "reversal_mode_counts": {
            "abc": sum(1 for t in trades if t.get("reversal_confirmation") == "abc"),
            "legacy": sum(1 for t in trades if t.get("reversal_confirmation") == "legacy"),
        },
        "sweep_mode_counts": {
            "structure": sum(1 for t in trades if t.get("sweep_confirmation") == "structure"),
            "legacy": sum(1 for t in trades if t.get("sweep_confirmation") == "legacy"),
        },
        "continuation_mode_counts": {
            "price_action": sum(1 for t in trades if t.get("continuation_confirmation") == "price_action"),
            "legacy": sum(1 for t in trades if t.get("continuation_confirmation") == "legacy"),
        },
    }


def _run_worker(payload):
    """Run one symbol in a child process so each worker owns one Twisted reactor."""
    symbol, kwargs = payload
    return symbol, run(symbol, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol")
    parser.add_argument("--all-pairs", action="store_true")
    parser.add_argument("--pairs", default="EURUSD,GBPUSD,USDJPY,USDCHF,USDCAD,AUDUSD,NZDUSD")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--mode", choices=["strict", "hybrid"], default="hybrid")
    parser.add_argument("--cache-dir", default="data/ctrader_cache")
    parser.add_argument("--disable-breaker", action="store_true")
    parser.add_argument("--disable-ote", action="store_true")
    parser.add_argument("--disable-mitigation", action="store_true")
    parser.add_argument("--min-confluence", type=int, default=0)
    parser.add_argument("--reversal-mode", choices=["abc", "legacy"], default="abc",
                        help="Hybrid reversal confirmation variant for controlled A/B testing.")
    parser.add_argument("--continuation-mode", choices=["price_action", "legacy"], default="price_action",
                        help="Hybrid continuation confirmation variant for controlled A/B testing.")
    parser.add_argument("--sweep-mode", choices=["structure", "legacy"], default="structure",
                        help="Hybrid liquidity-sweep level variant for controlled A/B testing.")
    parser.add_argument("--json")
    args = parser.parse_args()

    if not args.symbol and not args.all_pairs:
        parser.error("provide --symbol SYMBOL or --all-pairs")

    pairs = [args.symbol] if args.symbol else [
        p.strip().upper() for p in args.pairs.split(",") if p.strip()
    ]

    run_args = {
        "start": dt(args.start),
        "end": dt(args.end),
        "mode": args.mode,
        "cache_dir": args.cache_dir,
        "enable_breaker": not args.disable_breaker,
        "enable_ote": not args.disable_ote,
        "enable_mitigation": not args.disable_mitigation,
        "min_confluence": args.min_confluence,
        "reversal_mode": args.reversal_mode,
        "continuation_mode": args.continuation_mode,
        "sweep_mode": args.sweep_mode,
    }

    if len(pairs) > 1:
        workers = max(1, min(
            len(pairs),
            int(os.getenv("CTRADER_BACKTEST_WORKERS", "2")),
        ))
        ctx = mp.get_context("spawn")
        payloads = [(symbol, run_args) for symbol in pairs]
        with ctx.Pool(processes=workers) as pool:
            results = pool.map(_run_worker, payloads)
    else:
        results = [_run_worker((pairs[0], run_args))]

    reports = {}
    all_trades = []
    for symbol, trades in results:
        reports[symbol] = metrics(trades)
        all_trades.extend(trades)

    report = {
        "symbols": pairs,
        "mode": args.mode,
        "start": args.start,
        "end": args.end,
        "data_source": "cTrader Open API historical H1/H4",
        "reversal_mode": args.reversal_mode,
        "continuation_mode": args.continuation_mode,
        "sweep_mode": args.sweep_mode,
        "future_leak_guard": True,
        "pairs": reports,
        "aggregate": metrics(all_trades),
        "advanced_confluence": {
            "breaker": not args.disable_breaker,
            "ote": not args.disable_ote,
            "mitigation": not args.disable_mitigation,
            "min_confluence": args.min_confluence,
        },
    }

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(report, indent=2))

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
