"""Historical backtest runner using Exness MT5 data.

The runner is data-only: it never sends an order to Exness.
It evaluates the strategy on closed candles and records deterministic
trade outcomes. Entry is the FVG midpoint; stop/target come from strategy.
"""
import argparse
import csv
import json
from datetime import datetime, timezone

from data.exness_mt5 import ExnessMT5Data
from strategy.ict_strategy import evaluate_ict_2022


def _parse_dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _session_for_hour(dt):
    h = dt.hour
    if 7 <= h < 12:
        return "london"
    if 12 <= h < 13:
        return "overlap"
    if 13 <= h < 17:
        return "new_york"
    return "other"


def _outcome(candles, start_idx, side, entry, stop, target):
    """Walk forward one bar at a time. If SL and TP hit in same bar, count SL
    first (conservative; OHLC alone cannot establish intrabar order)."""
    for i in range(start_idx + 1, len(candles)):
        c = candles[i]
        if side == "LONG":
            hit_stop = c["low"] <= stop
            hit_target = c["high"] >= target
        else:
            hit_stop = c["high"] >= stop
            hit_target = c["low"] <= target

        if hit_stop and hit_target:
            return "SL", i, stop
        if hit_stop:
            return "SL", i, stop
        if hit_target:
            return "TP", i, target
    return "OPEN", len(candles) - 1, candles[-1]["close"]


def _merge_4h_context(candles_4h, time_value):
    t = _parse_dt(time_value)
    # Only 4H candles that closed at or before the execution candle are allowed.
    return [c for c in candles_4h if _parse_dt(c["time"]) <= t]


def run(symbol, start, end, account_equity=10000.0, risk_pct=0.005):
    feed = ExnessMT5Data()
    try:
        h1 = feed.fetch(symbol, "H1", start, end)
        h4 = feed.fetch(symbol, "H4", start, end)
        if len(h1) < 100 or len(h4) < 40:
            raise RuntimeError(f"Not enough data: H1={len(h1)}, H4={len(h4)}")

        trades = []
        last_exit = -1

        for i in range(60, len(h1) - 1):
            if i <= last_exit:
                continue
            current = h1[i]
            session = _session_for_hour(_parse_dt(current["time"]))
            if session not in ("london", "new_york", "overlap"):
                continue

            h1_window = h1[:i + 1]
            h4_window = _merge_4h_context(h4, current["time"])
            if len(h4_window) < 30:
                continue

            setup = evaluate_ict_2022(
                h1_window,
                h4_window,
                symbol,
                session_context=session,
            )
            if not setup:
                continue

            entry = setup["entry_mid"]
            stop = setup["stop_price"]
            target = setup["tp_target"]
            outcome, exit_idx, exit_price = _outcome(
                h1, i, setup["side"], entry, stop, target
            )
            risk_distance = abs(entry - stop)
            pnl_r = 0.0 if risk_distance <= 0 else (
                (exit_price - entry) / risk_distance
                if setup["side"] == "LONG"
                else (entry - exit_price) / risk_distance
            )

            trades.append({
                "pair": symbol,
                "time_utc": current["time"],
                "side": setup["side"],
                "entry": entry,
                "stop": stop,
                "tp1": target,
                "tp2": target,
                "outcome": outcome,
                "pnl_r": pnl_r,
                "rr": setup["rr"],
                "exit_time_utc": h1[exit_idx]["time"],
            })
            last_exit = exit_idx

        return trades
    finally:
        feed.shutdown()


def metrics(trades, account_equity=10000.0, risk_pct=0.005):
    if not trades:
        return {"trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
                "expectancy_r": 0.0, "max_drawdown_pct": 0.0}

    wins = [t["pnl_r"] for t in trades if t["pnl_r"] > 0]
    losses = [t["pnl_r"] for t in trades if t["pnl_r"] < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        equity += t["pnl_r"] * risk_pct * 100.0
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(trades),
        "profit_factor": gross_win / gross_loss if gross_loss else float("inf"),
        "expectancy_r": sum(t["pnl_r"] for t in trades) / len(trades),
        "max_drawdown_pct": max_dd,
        "account_equity_start": account_equity,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="EURUSD")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--csv", default=None)
    p.add_argument("--json", default=None)
    args = p.parse_args()

    trades = run(args.symbol, _parse_dt(args.start), _parse_dt(args.end))
    report = metrics(trades)
    if args.csv:
        with open(args.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(trades[0].keys()) if trades else [
                "pair","time_utc","side","entry","stop","tp1","tp2","outcome","pnl_r","rr","exit_time_utc"
            ])
            w.writeheader()
            w.writerows(trades)
    if args.json:
        with open(args.json, "w") as f:
            json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
