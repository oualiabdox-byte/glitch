"""Backtest runner using B2TRADER guest historical candles.

The strategy modules are imported unchanged. This runner only supplies normalized
1H/4H candles and reuses the existing ICT backtest mechanics.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from data.b2trader import B2TRADERGuestData
from strategy.ict_strategy import evaluate_ict_2022
from strategy.ict_hybrid import evaluate_ict_hybrid


def dt(v):
    return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(timezone.utc)


def run(symbol, market_symbol, start, end, mode="strict", base_url=None, cache_dir="data/b2trader_cache"):
    feed = B2TRADERGuestData(base_url, cache_dir=cache_dir)
    h1 = feed.cached_history(market_symbol, "1h", start, end)
    h4 = feed.cached_history(market_symbol, "4h", start, end)

    if len(h1) < 100 or len(h4) < 40:
        raise RuntimeError(f"Not enough B2TRADER data: H1={len(h1)}, H4={len(h4)}")

    fn = evaluate_ict_2022 if mode == "strict" else evaluate_ict_hybrid
    trades = []

    # Preserve the existing strategy contract. The signal is evaluated on
    # closed candles; this runner does not alter strategy parameters.
    for i in range(60, len(h1) - 1):
        setup = fn(h1[:i + 1], h4, symbol, session_context="london") if mode == "strict" else fn(h1[:i + 1], h4, symbol)
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
        for j in range(entry_idx, len(h1)):
            c = h1[j]
            sl = c["low"] <= stop if side == "LONG" else c["high"] >= stop
            tp = c["high"] >= target if side == "LONG" else c["low"] <= target
            if sl:
                outcome, exit_price, exit_time = "SL", stop, c["time"]
                break
            if tp:
                outcome, exit_price, exit_time = "TP", target, c["time"]
                break

        risk = abs(entry - stop)
        pnl_r = ((exit_price - entry) / risk if side == "LONG" else (entry - exit_price) / risk) if risk else 0.0
        trades.append({
            "pair": symbol,
            "market_symbol": market_symbol,
            "mode": mode,
            "signal_time_utc": h1[i]["time"],
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
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", required=True)
    p.add_argument("--market-symbol", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--mode", choices=["strict", "hybrid"], default="strict")
    p.add_argument("--base-url")
    p.add_argument("--cache-dir", default="data/b2trader_cache")
    p.add_argument("--json")
    a = p.parse_args()

    trades = run(a.symbol, a.market_symbol, dt(a.start), dt(a.end), a.mode, a.base_url, a.cache_dir)
    report = metrics(trades)
    report.update({
        "symbol": a.symbol,
        "market_symbol": a.market_symbol,
        "mode": a.mode,
        "start": a.start,
        "end": a.end,
        "data_source": "B2TRADER guest historical candles",
        "strategy_changed": False,
    })
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
