"""Deterministic local cTrader backtest runner for the strict Forex ICT/SMC engine.

cTrader supplies historical H1/H4 data. The strategy is broker-independent.
No live orders are submitted by this module.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from data.ctrader import CTraderData
from strategy.ict_strategy import evaluate_ict_2022
from strategy import risk, safety, timing


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def h4_until(h4, timestamp):
    ts = dt(timestamp).timestamp()
    return [c for c in h4 if dt(c["time"]).timestamp() + 4 * 3600 <= ts]


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


def run(
    symbol,
    start,
    end,
    cache_dir="data/ctrader_cache",
    swing_length=3,
    max_trades_per_day=0,
    cooldown_minutes=0,
    max_drawdown_r=0.0,
    max_atr_spike=0.0,
    news_events=None,
    news_pause_before=45,
    news_pause_after=20,
):
    feed = CTraderData()
    data = load_or_download(feed, symbol, start, end, cache_dir)
    h1, h4 = data["h1"], data["h4"]

    if len(h1) < 100 or len(h4) < 40:
        raise RuntimeError(f"Not enough cTrader data: H1={len(h1)}, H4={len(h4)}")

    trades = []
    next_available_idx = 60
    last_entry_time = None
    equity_r = 0.0
    peak_equity_r = 0.0

    for i in range(60, len(h1) - 1):
        if i < next_available_idx:
            continue

        signal_time = h1[i]["time"]
        session = timing.session_context(signal_time).session
        window = h1[: i + 1]

        if max_atr_spike > 0 and safety.abnormal_volatility(window, max_ratio=max_atr_spike):
            continue
        if safety.news_blocked(
            signal_time,
            symbol,
            news_events or [],
            pause_before_minutes=news_pause_before,
            pause_after_minutes=news_pause_after,
        ):
            continue
        if max_trades_per_day > 0 and risk.trades_on_day(trades, signal_time) >= max_trades_per_day:
            continue
        if not risk.cooldown_clear(last_entry_time, signal_time, cooldown_minutes):
            continue
        if not risk.drawdown_guard(equity_r, peak_equity_r, max_drawdown_r):
            continue

        h4_visible = h4_until(h4, signal_time)
        if len(h4_visible) < 30:
            continue

        setup = evaluate_ict_2022(
            h1[: i + 1],
            h4_visible,
            symbol,
            session_context=session,
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
            if sl:
                outcome, exit_price, exit_time, exit_idx = "SL", stop, candle["time"], j
                break
            if tp:
                outcome, exit_price, exit_time, exit_idx = "TP", target, candle["time"], j
                break

        next_available_idx = max(next_available_idx, exit_idx + 1)
        risk_distance = abs(entry - stop)
        pnl_r = (
            ((exit_price - entry) / risk_distance if side == "LONG" else (entry - exit_price) / risk_distance)
            if risk_distance else 0.0
        )
        last_entry_time = signal_time
        equity_r += pnl_r
        peak_equity_r = max(peak_equity_r, equity_r)

        trades.append({
            "pair": symbol,
            "signal_time_utc": signal_time,
            "entry_time_utc": h1[entry_idx]["time"],
            "side": side,
            "entry": entry,
            "stop": stop,
            "target": target,
            "outcome": outcome,
            "pnl_r": pnl_r,
            "rr": setup["rr"],
            "session": setup["session"],
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
    return {
        "trades": len(rs),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(rs) if rs else 0.0,
        "profit_factor": sum(wins) / gross_loss if gross_loss else 0.0,
        "expectancy_r": sum(rs) / len(rs) if rs else 0.0,
        "max_drawdown_r": drawdown,
        "net_r": sum(rs),
    }


def main():
    parser = argparse.ArgumentParser(description="Local cTrader Forex ICT/SMC backtest")
    parser.add_argument("--symbol")
    parser.add_argument("--all-pairs", action="store_true")
    parser.add_argument("--pairs", default="EURUSD,GBPUSD,USDJPY,USDCHF,USDCAD,AUDUSD,NZDUSD")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--cache-dir", default="data/ctrader_cache")
    parser.add_argument("--swing-length", type=int, default=3)
    parser.add_argument("--max-trades-per-day", type=int, default=0)
    parser.add_argument("--cooldown-minutes", type=int, default=0)
    parser.add_argument("--max-drawdown-r", type=float, default=0.0)
    parser.add_argument("--max-atr-spike", type=float, default=0.0)
    parser.add_argument("--news-events-json", default="")
    parser.add_argument("--news-pause-before", type=int, default=45)
    parser.add_argument("--news-pause-after", type=int, default=20)
    parser.add_argument("--json")
    args = parser.parse_args()

    if not args.symbol and not args.all_pairs:
        parser.error("provide --symbol SYMBOL or --all-pairs")

    pairs = [args.symbol.upper()] if args.symbol else [p.strip().upper() for p in args.pairs.split(",") if p.strip()]
    news_events = safety.load_news_events(Path(args.news_events_json).read_text()) if args.news_events_json else []

    reports = {}
    all_trades = []
    for symbol in pairs:
        trades = run(
            symbol,
            dt(args.start),
            dt(args.end),
            cache_dir=args.cache_dir,
            swing_length=args.swing_length,
            max_trades_per_day=args.max_trades_per_day,
            cooldown_minutes=args.cooldown_minutes,
            max_drawdown_r=args.max_drawdown_r,
            max_atr_spike=args.max_atr_spike,
            news_events=news_events,
            news_pause_before=args.news_pause_before,
            news_pause_after=args.news_pause_after,
        )
        reports[symbol] = metrics(trades)
        all_trades.extend(trades)

    report = {
        "symbols": pairs,
        "start": args.start,
        "end": args.end,
        "mode": "strict_ict_smc",
        "data_source": "cTrader Open API historical H1/H4",
        "future_leak_guard": True,
        "swing_length": args.swing_length,
        "risk_gates": {
            "max_trades_per_day": args.max_trades_per_day,
            "cooldown_minutes": args.cooldown_minutes,
            "max_drawdown_r": args.max_drawdown_r,
            "max_atr_spike": args.max_atr_spike,
            "news_pause_before": args.news_pause_before,
            "news_pause_after": args.news_pause_after,
        },
        "pairs": reports,
        "aggregate": metrics(all_trades),
    }

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(report, indent=2))

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
