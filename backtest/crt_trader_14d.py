#!/usr/bin/env python3
"""Run the CRT/TBS trader adapter on saved cTrader M5 datasets.

This is signal-only research. It reads the repository's existing cTrader
JSON files, aggregates them to completed 2-hour CRT candles, and writes trade
logs plus per-pair metrics. Gold is reported as unavailable when no local
XAUUSD/GC=F dataset exists; it is never silently substituted.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.crt_trader import CrtTbsTrader


def load_frame(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text())
    frame = pd.DataFrame(payload["candles"])
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    frame = frame.sort_values("time").drop_duplicates("time").set_index("time")
    return frame[["open", "high", "low", "close", "volume"]].astype(float)


def metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(row["r_multiple"]) for row in rows]
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    gross_loss = abs(sum(losses))
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    losing_streak = 0
    longest_losing_streak = 0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
        if value < 0:
            losing_streak += 1
            longest_losing_streak = max(longest_losing_streak, losing_streak)
        else:
            losing_streak = 0
    return {
        "trades": len(values),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(100 * len(wins) / len(values), 2) if values else 0.0,
        "total_r": round(sum(values), 6),
        "avg_r": round(sum(values) / len(values), 6) if values else 0.0,
        "profit_factor": round(sum(wins) / gross_loss, 6) if gross_loss else ("inf" if wins else None),
        "max_drawdown_r": round(drawdown, 6),
        "longest_losing_streak": longest_losing_streak,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=None)
    parser.add_argument("--suffix", default="14d")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "backtest" / "ctrader_volume_data")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "backtest" / "crt_trader_14d_results")
    args = parser.parse_args()
    if args.days is not None and args.days <= 0:
        raise SystemExit("--days must be positive")
    trader = CrtTbsTrader()
    all_trades: list[dict[str, Any]] = []
    by_pair: dict[str, dict[str, Any]] = {}
    diagnostics_by_pair: dict[str, dict[str, int]] = {}
    files = sorted(args.data_dir.glob(f"*_m5_{args.suffix}.json"))
    if not files:
        raise SystemExit(f"No cTrader M5 files found in {args.data_dir}")
    for path in files:
        payload = json.loads(path.read_text())
        pair = str(payload.get("pair") or path.name.split("_")[0]).upper()
        frame = load_frame(path)
        diagnostics: dict[str, int] = {}
        trades = trader.signals(frame, pair, pair, diagnostics)
        for row in trades:
            row["instrument"] = pair
            row["source_file"] = path.name
        all_trades.extend(trades)
        by_pair[pair] = metrics(trades)
        diagnostics_by_pair[pair] = diagnostics
    known_gold = [p for p in files if any(token in p.name.upper() for token in ("XAU", "GOLD", "GC"))]
    missing = {"GOLD": "No local XAUUSD/GC=F cTrader dataset; not substituted"} if not known_gold else {}
    total = metrics(sorted(all_trades, key=lambda row: row["exit_time"]))
    summary = {
        "strategy": trader.report(),
        "data_source": "repository cTrader M5 JSON fixtures",
        "period": args.suffix,
        "pairs_tested": sorted(by_pair),
        "not_tested": missing,
        "by_pair": by_pair,
        "diagnostics": diagnostics_by_pair,
        "total": total,
        "limitations": [
            f"{args.suffix} is a limited research sample",
            "cTrader trendbar OHLC cannot reveal intrabar stop/target ordering",
            "the fixture does not contain bid/ask spread or slippage",
            "this runner does not submit orders or modify execution/demo code",
        ],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    pd.DataFrame(all_trades).to_csv(args.output_dir / "trades.csv", index=False)
    diagnostic_rows = []
    for pair, diagnostics in diagnostics_by_pair.items():
        row = {"pair": pair}
        row.update(diagnostics)
        diagnostic_rows.append(row)
    pd.DataFrame(diagnostic_rows).to_csv(args.output_dir / "diagnostics.csv", index=False)
    lines = [f"# CRT/TBS trader — cTrader {args.suffix} research test", "", "## Configuration", "", f"- `{json.dumps(trader.report(), sort_keys=True)}`", "", "## Results", "", "| Pair | Trades | Win rate | Total R | Profit factor | Max DD (R) |", "|---|---:|---:|---:|---:|---:|"]
    for pair in sorted(by_pair):
        row = by_pair[pair]
        lines.append(f"| {pair} | {row['trades']} | {row['win_rate_pct']:.2f}% | {row['total_r']:.4f} | {row['profit_factor']} | {row['max_drawdown_r']:.4f} |")
    lines += ["", f"**Total:** {total['trades']} trades, `{total['total_r']:.4f}R`.", "", "## Diagnostic funnel", "", "See `diagnostics.csv` and the `diagnostics` field in `summary.json` for per-pair stage counts.", "", "## Coverage", "", *[f"- {key}: {value}" for key, value in missing.items()], "", "## Caveats", "", *[f"- {item}" for item in summary["limitations"]], ""]
    (args.output_dir / "report.md").write_text("\n".join(lines))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
