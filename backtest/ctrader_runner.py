"""cTrader historical backtest runner for the existing ICT/SMC strategy."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone, timedelta

from data.ctrader import CTraderData
from strategy.ict_hybrid import evaluate_ict_hybrid


def dt(v):
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(timezone.utc)


def h4_closed(h4, timestamp):
    ts = dt(timestamp).timestamp()
    return [c for c in h4 if dt(c["time"]).timestamp() + 4 * 3600 <= ts]


def simulate(h1, h4, symbol):
    trades = []
    next_available = 60

    for i in range(60, len(h1) - 1):
        if i < next_available:
            continue
        visible_h4 = h4_closed(h4, h1[i]["time"])
        if len(visible_h4) < 30:
            continue

        setup = evaluate_ict_hybrid(h1[: i + 1], visible_h4, symbol)
        if not setup:
            continue

        entry_i = i + 1
        entry = h1[entry_i]["open"]
        side = setup["side"]
        stop = setup["stop_price"]
        target = setup["tp_target"]

        if (side == "LONG" and entry <= stop) or (side == "SHORT" and entry >= stop):
            continue

        outcome = "OPEN"
        exit_price = h1[-1]["close"]
        exit_time = h1[-1]["time"]
        exit_i = len(h1) - 1

        for j in range(entry_i, len(h1)):
            c = h1[j]
            hit_sl = c["low"] <= stop if side == "LONG" else c["high"] >= stop
            hit_tp = c["high"] >= target if side == "LONG" else c["low"] <= target
            # Conservative intrabar rule: if both are touched in one candle,
            # count the stop first because tick ordering is unknown.
            if hit_sl:
                outcome, exit_price, exit_time, exit_i = "SL", stop, c["time"], j
                break
            if hit_tp:
                outcome, exit_price, exit_time, exit_i = "TP", target, c["time"], j
                break

        risk = abs(entry - stop)
        pnl_r = (
            ((exit_price - entry) / risk)
            if side == "LONG"
            else ((entry - exit_price) / risk)
        ) if risk else 0.0

        trades.append({
            "pair": symbol,
            "signal_time_utc": h1[i]["time"],
            "entry_time_utc": h1[entry_i]["time"],
            "exit_time_utc": exit_time,
            "side": side,
            "entry": entry,
            "stop": stop,
            "target": target,
            "outcome": outcome,
            "pnl_r": pnl_r,
            "rr": setup["rr"],
            "entry_model": setup.get("entry_model"),
            "entry_trigger": setup.get("entry_trigger"),
            "event_type": setup.get("event_type"),
            "confluence_score": setup.get("confluence_score"),
        })
        next_available = exit_i + 1

    return trades


def metrics(trades):
    rs = [float(t["pnl_r"]) for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r < 0]
    equity = peak = max_dd = 0.0
    for r in rs:
        equity += r
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    gross_loss = abs(sum(losses))
    return {
        "trades": len(rs),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(rs) if rs else 0.0,
        "profit_factor": sum(wins) / gross_loss if gross_loss else 0.0,
        "expectancy_r": sum(rs) / len(rs) if rs else 0.0,
        "net_r": sum(rs),
        "max_drawdown_r": max_dd,
    }


def run(symbol, start, end):
    feed = CTraderData()
    data = feed.download(symbol, start, end, periods=("h1", "h4"))
    h1, h4 = data["h1"], data["h4"]
    if len(h1) < 100 or len(h4) < 40:
        raise RuntimeError(f"Not enough cTrader data: H1={len(h1)}, H4={len(h4)}")
    trades = simulate(h1, h4, symbol)
    report = metrics(trades)
    report.update({
        "symbol": symbol,
        "start": dt(start).isoformat(),
        "end": dt(end).isoformat(),
        "data_source": "cTrader Open API historical trendbars",
        "future_leak_guard": True,
        "candles_h1": len(h1),
        "candles_h4": len(h4),
        "trades_detail": trades,
    })
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument("--days", type=int, default=120)
    p.add_argument("--start")
    p.add_argument("--end")
    args = p.parse_args()

    end = dt(args.end) if args.end else datetime.now(timezone.utc)
    start = dt(args.start) if args.start else end - timedelta(days=args.days)
    report = run(args.symbol, start, end)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
