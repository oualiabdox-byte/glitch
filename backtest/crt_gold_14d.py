#!/usr/bin/env python3
"""Gold-only CRT/TBS 14-day research backtest.

Uses Yahoo Finance ``GC=F`` gold futures as a transparent public proxy for
XAUUSD. This runner intentionally excludes all forex pairs from the active
research scope.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest.crt_tbs_14d import backtest, fetch_5m  # noqa: E402


def main() -> int:
    days = 14
    end = pd.Timestamp.now(tz="UTC").floor("5min")
    start = end - pd.Timedelta(days=days)
    symbol = "GC=F"
    instrument = "GOLD"
    print(f"Downloading {instrument} ({symbol}) {start.isoformat()} -> {end.isoformat()}", flush=True)
    frame = fetch_5m(symbol, start, end)
    trades, quality = backtest(instrument, symbol, frame)
    values = [float(row.r_multiple) for row in trades]
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    gross_loss = abs(sum(losses))
    equity = peak = max_dd = 0.0
    losing_streak = longest_losing_streak = 0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
        if value < 0:
            losing_streak += 1
            longest_losing_streak = max(longest_losing_streak, losing_streak)
        else:
            losing_streak = 0
    metrics = {
        "trades": len(values), "wins": len(wins), "losses": len(losses),
        "win_rate_pct": round(100 * len(wins) / len(values), 2) if values else 0.0,
        "total_r": round(sum(values), 6),
        "avg_r": round(sum(values) / len(values), 6) if values else 0.0,
        "profit_factor": round(sum(wins) / gross_loss, 6) if gross_loss else ("inf" if wins else None),
        "max_drawdown_r": round(max_dd, 6),
        "longest_losing_streak": longest_losing_streak,
    }
    summary = {
        "scope": "GOLD_ONLY",
        "instrument": instrument,
        "symbol": symbol,
        "period_start_utc": start.isoformat(),
        "period_end_utc": end.isoformat(),
        "data_quality": quality,
        "metrics": metrics,
        "trades": [trade.__dict__ for trade in trades],
        "limitations": [
            "14 calendar days is a small sample",
            "GC=F is a gold-futures proxy, not broker-specific XAUUSD",
            "Yahoo OHLC is indicative and excludes spread, slippage, commission, and financing",
            "intrabar stop/target ordering is unknowable from OHLC",
        ],
    }
    output = ROOT / "backtest" / "crt_gold_14d_results"
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    pd.DataFrame(summary["trades"]).to_csv(output / "trades.csv", index=False)
    report = "\n".join([
        "# Gold-only CRT/TBS 14-day research test", "",
        f"Period: `{start.isoformat()}` to `{end.isoformat()}`", "",
        "- Instrument: `GOLD`", "- Data proxy: `GC=F`", "- HTF: completed 2H CRT purge",
        "- Entry: M5 body-close TBS followed by re-entry", "- Structure filter: 2–6 M5 candles",
        "- Management: 50% at equilibrium, remainder breakeven, opposite CRT boundary", "",
        "| Trades | Win rate | Total R | Average R | Profit factor | Max DD (R) | Longest losing streak |",
        "|---:|---:|---:|---:|---:|---:|---:|",
        f"| {metrics['trades']} | {metrics['win_rate_pct']:.2f}% | {metrics['total_r']:.4f} | {metrics['avg_r']:.4f} | {metrics['profit_factor']} | {metrics['max_drawdown_r']:.4f} | {metrics['longest_losing_streak']} |",
        "", "## Caveats", "", *[f"- {item}" for item in summary["limitations"]], "",
    ])
    (output / "report.md").write_text(report)
    print(json.dumps({"scope": "GOLD_ONLY", "metrics": metrics, "data_quality": quality}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
