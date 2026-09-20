"""ICT/SMC backtest using Exness public historical tick data. No MT5/login.

Execution is deliberately conservative:
- signal is evaluated only on a closed H1 candle
- entry occurs at the next H1 bar open (ask for long, bid for short)
- exits use bid/ask OHLC
- the entry signal candle is never used to claim a fill at an intrabar price
"""
import argparse
import csv
import json
from datetime import datetime, timezone, timedelta

from data.exness_ticks import ExnessTickData
from strategy.ict_strategy import evaluate_ict_2022
from strategy.ict_hybrid import evaluate_ict_hybrid


def dt(v):
    return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(timezone.utc)


def session_for(t):
    h = t.hour
    return (
        "london" if 7 <= h < 12
        else "overlap" if 12 <= h < 13
        else "new_york" if 13 <= h < 17
        else "other"
    )


def _entry_price(candle, side):
    if side == "LONG":
        return candle.get("ask_open", candle["open"])
    return candle.get("bid_open", candle["open"])


def outcome(candles, entry_idx, side, stop, target):
    """Resolve exits from the first candle after the signal.

    If both stop and target are touched in the same candle, stop wins. This is
    conservative because OHLC data cannot reveal the intrabar ordering.
    """
    for j in range(entry_idx, len(candles)):
        c = candles[j]
        sl = (
            c.get("bid_low", c["low"]) <= stop
            if side == "LONG"
            else c.get("ask_high", c["high"]) >= stop
        )
        tp = (
            c.get("bid_high", c["high"]) >= target
            if side == "LONG"
            else c.get("ask_low", c["low"]) <= target
        )
        if sl:
            return "SL", j, stop
        if tp:
            return "TP", j, target

    px = (
        candles[-1].get("bid_close", candles[-1]["close"])
        if side == "LONG"
        else candles[-1].get("ask_close", candles[-1]["close"])
    )
    return "OPEN", len(candles) - 1, px


def run(symbol, start, end, mode="strict", cache_dir="data/exness_cache"):
    feed = ExnessTickData(cache_dir)
    h1 = feed.bars(symbol, start, end, "1H")
    h4 = feed.bars(symbol, start, end, "4H")

    if len(h1) < 100 or len(h4) < 40:
        raise RuntimeError(
            f"Not enough Exness data: H1={len(h1)}, H4={len(h4)}"
        )

    fn = evaluate_ict_2022 if mode == "strict" else evaluate_ict_hybrid
    trades = []
    last_exit = -1

    for i in range(60, len(h1) - 1):
        if i <= last_exit:
            continue

        t = dt(h1[i]["time"])
        s = session_for(t)
        if mode == "strict" and s not in ("london", "new_york", "overlap"):
            continue

        close_time = t + timedelta(hours=1)
        h4c = [
            c for c in h4
            if dt(c["time"]) + timedelta(hours=4) <= close_time
        ]
        if len(h4c) < 30:
            continue

        setup = (
            fn(h1[:i + 1], h4c, symbol, session_context=s)
            if mode == "strict"
            else fn(h1[:i + 1], h4c, symbol)
        )
        if not setup:
            continue

        entry_idx = i + 1
        if entry_idx >= len(h1):
            continue

        side = setup["side"]
        entry = _entry_price(h1[entry_idx], side)
        stop = setup["stop_price"]
        target = setup["tp_target"]

        # Skip a setup whose next-bar opening price invalidates the structure.
        if (side == "LONG" and entry <= stop) or (side == "SHORT" and entry >= stop):
            continue

        result, ei, px = outcome(h1, entry_idx, side, stop, target)
        risk = abs(entry - stop)
        r = (
            (px - entry) / risk
            if side == "LONG"
            else (entry - px) / risk
        ) if risk else 0.0

        trades.append({
            "pair": symbol,
            "mode": mode,
            "signal_time_utc": h1[i]["time"],
            "entry_time_utc": h1[entry_idx]["time"],
            "side": side,
            "entry": entry,
            "stop": stop,
            "tp1": target,
            "tp2": target,
            "outcome": result,
            "pnl_r": r,
            "rr": setup["rr"],
            "spread_avg_signal": h1[i].get("spread_avg", 0.0),
            "spread_avg_entry": h1[entry_idx].get("spread_avg", 0.0),
            "entry_trigger": setup.get("entry_trigger", "STRICT"),
            "exit_time_utc": h1[ei]["time"],
        })
        last_exit = ei

    return trades


def metrics(trades):
    rs = [t["pnl_r"] for t in trades]
    w = [r for r in rs if r > 0]
    l = [r for r in rs if r < 0]
    eq = peak = dd = 0.0

    for r in rs:
        eq += r
        peak = max(peak, eq)
        dd = max(dd, peak - eq)

    gross_loss = abs(sum(l))
    return {
        "trades": len(rs),
        "wins": len(w),
        "losses": len(l),
        "win_rate": len(w) / len(rs) if rs else 0,
        "profit_factor": sum(w) / gross_loss if gross_loss else 0,
        "expectancy_r": sum(rs) / len(rs) if rs else 0,
        "avg_r": sum(rs) / len(rs) if rs else 0,
        "max_drawdown_r": dd,
        "net_r": sum(rs),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--mode", choices=["strict", "hybrid"], default="strict")
    p.add_argument("--csv")
    p.add_argument("--json")
    a = p.parse_args()

    trades = run(a.symbol, dt(a.start), dt(a.end), a.mode)
    report = metrics(trades)

    if a.csv:
        fields = [
            "pair", "mode", "signal_time_utc", "entry_time_utc", "side",
            "entry", "stop", "tp1", "tp2", "outcome", "pnl_r", "rr",
            "spread_avg_signal", "spread_avg_entry", "entry_trigger",
            "exit_time_utc",
        ]
        with open(a.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(trades)

    if a.json:
        with open(a.json, "w") as f:
            json.dump(report, f, indent=2)

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
