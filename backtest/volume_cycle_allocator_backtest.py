#!/usr/bin/env python3
"""Run the Volume-Cycle Adaptive Allocator on saved cTrader JSON datasets."""
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from strategy.volume_cycle_allocator import (
    AdaptiveAllocator,
    AllocatorConfig,
    VolumeCycle,
    build_volume_cycles,
    max_drawdown,
    validate_volume_bars,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("backtest/ctrader_volume_data"))
    parser.add_argument("--output-dir", type=Path, default=Path("backtest/volume_cycle_allocator_run"))
    parser.add_argument("--cycle-bars", type=int, default=96, help="Target volume equivalent in M5 bars")
    parser.add_argument("--history-cycles", type=int, default=6)
    return parser.parse_args()


def _load_data(data_dir: Path) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(data_dir.glob("*_m5_10d.json")):
        payload = json.loads(path.read_text())
        pair = str(payload.get("pair") or path.name.split("_")[0]).upper()
        bars = payload["candles"]
        report = validate_volume_bars(bars, pair)
        if not report["valid"]:
            raise ValueError(f"{pair} failed validation: {report['errors'][:3]}")
        result[pair] = bars
    if len(result) < 2:
        raise ValueError("at least two cTrader pair datasets are required")
    return result


def _metrics(equity: list[float], returns: list[float]) -> dict[str, float | int | None]:
    if not equity:
        return {"bars": 0, "total_return_pct": None, "max_drawdown_pct": None, "win_rate_pct": None, "sharpe_unannualized": None}
    positive = [value for value in returns if value != 0]
    mean = sum(positive) / len(positive) if positive else 0.0
    variance = sum((value - mean) ** 2 for value in positive) / max(1, len(positive) - 1)
    stdev = math.sqrt(variance)
    return {
        "bars": len(returns),
        "total_return_pct": (equity[-1] - 1.0) * 100.0,
        "max_drawdown_pct": max_drawdown(equity) * 100.0,
        "win_rate_pct": (sum(value > 0 for value in positive) / len(positive) * 100.0) if positive else None,
        "sharpe_unannualized": (mean / stdev) if stdev > 0 else None,
    }


def _write_cycles(path: Path, cycles: list[VolumeCycle]) -> None:
    fields = list(VolumeCycle.__dataclass_fields__)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for cycle in cycles:
            writer.writerow(cycle.as_dict())


def _write_report(path: Path, summary: dict[str, Any]) -> None:
    adaptive = summary["adaptive"]
    equal = summary["equal_weight"]
    lines = [
        "# Volume-Cycle Adaptive Allocator Backtest",
        "",
        "> This is a research backtest on cTrader trendbar OHLC plus native tick volume. It is not an execution or profitability guarantee.",
        "",
        "## Method",
        "",
        "- Each pair forms a cycle when cumulative positive volume reaches the median prior-volume quota multiplied by `cycle_bars`.",
        "- The first warm-up window is calibration-only.",
        "- A completed cycle contributes its close-to-close return to that pair's history.",
        "- Weights for the next bar use only previously completed cycles; no future bar is used.",
        "- Positive EWMA cycle momentum is scaled by mean absolute cycle return, capped per pair, and normalized.",
        "- The benchmark is equal weight across all available pairs at every bar.",
        "",
        "## Data",
        "",
        f"- Pairs: {', '.join(summary['pairs'])}",
        f"- Common M5 timestamps: {summary['common_timestamps']}",
        f"- Common period: {summary['first_timestamp']} to {summary['last_timestamp']}",
        f"- Completed volume cycles: {summary['completed_cycles']}",
        "",
        "## Results",
        "",
        "| Portfolio | Total return | Max drawdown | Win rate | Unannualized Sharpe | Bars |",
        "|---|---:|---:|---:|---:|---:|",
        f"| Adaptive | {adaptive['total_return_pct']:.4f}% | {adaptive['max_drawdown_pct']:.4f}% | {adaptive['win_rate_pct'] if adaptive['win_rate_pct'] is not None else 'n/a'}% | {adaptive['sharpe_unannualized'] if adaptive['sharpe_unannualized'] is not None else 'n/a'} | {adaptive['bars']} |",
        f"| Equal weight | {equal['total_return_pct']:.4f}% | {equal['max_drawdown_pct']:.4f}% | {equal['win_rate_pct'] if equal['win_rate_pct'] is not None else 'n/a'}% | {equal['sharpe_unannualized'] if equal['sharpe_unannualized'] is not None else 'n/a'} | {equal['bars']} |",
        "",
        "## Reproducibility",
        "",
        f"- Configuration: `{json.dumps(summary['config'], sort_keys=True)}`",
        "- The input JSON files are retained under `backtest/ctrader_volume_data/` for subsequent runs.",
        "- Results are saved as JSON, CSV, and Markdown in the output directory.",
    ]
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    args = parse_args()
    data = _load_data(args.data_dir)
    pairs = sorted(data)
    timestamps = sorted(set.intersection(*(set(str(row["time"]) for row in data[pair]) for pair in pairs)))
    if len(timestamps) < 3:
        raise ValueError("not enough common timestamps")
    config = AllocatorConfig(target_cycle_bars=args.cycle_bars, history_cycles=args.history_cycles)
    cycles_by_pair = {pair: build_volume_cycles(pair, data[pair], config) for pair in pairs}
    all_cycles = [cycle for cycles in cycles_by_pair.values() for cycle in cycles]
    cycles_by_end: dict[str, list[VolumeCycle]] = {}
    for cycle in all_cycles:
        cycles_by_end.setdefault(cycle.end_time, []).append(cycle)

    allocator = AdaptiveAllocator(pairs, config)
    weights = {pair: 1.0 / len(pairs) for pair in pairs}
    previous_close: dict[str, float] | None = None
    adaptive_equity = [1.0]
    equal_equity = [1.0]
    adaptive_returns: list[float] = []
    equal_returns: list[float] = []
    equity_rows: list[dict[str, Any]] = []
    processed_cycles: set[tuple[str, int]] = set()
    turnover = 0.0

    for timestamp in timestamps:
        current_close = {pair: next(float(row["close"]) for row in data[pair] if str(row["time"]) == timestamp) for pair in pairs}
        if previous_close is None:
            previous_close = current_close
            equity_rows.append({"time": timestamp, "adaptive_equity": 1.0, "equal_equity": 1.0, **{f"weight_{pair}": weights[pair] for pair in pairs}})
            continue
        returns = {pair: current_close[pair] / previous_close[pair] - 1.0 for pair in pairs}
        adaptive_return = sum(weights[pair] * returns[pair] for pair in pairs)
        equal_return = sum(returns.values()) / len(pairs)
        adaptive_equity.append(adaptive_equity[-1] * (1.0 + adaptive_return))
        equal_equity.append(equal_equity[-1] * (1.0 + equal_return))
        adaptive_returns.append(adaptive_return)
        equal_returns.append(equal_return)

        # Update only after this bar's return has been booked.
        for cycle in cycles_by_end.get(timestamp, []):
            allocator.record_completed_cycle(cycle)
            processed_cycles.add((cycle.pair, cycle.cycle_id))
        new_weights = allocator.weights()
        turnover += sum(abs(new_weights[pair] - weights[pair]) for pair in pairs)
        weights = new_weights
        equity_rows.append({"time": timestamp, "adaptive_equity": adaptive_equity[-1], "equal_equity": equal_equity[-1], **{f"weight_{pair}": weights[pair] for pair in pairs}})
        previous_close = current_close

    summary = {
        "config": config.__dict__,
        "pairs": pairs,
        "common_timestamps": len(timestamps),
        "first_timestamp": timestamps[0],
        "last_timestamp": timestamps[-1],
        "completed_cycles": len(processed_cycles),
        "cycles_by_pair": {pair: len(cycles_by_pair[pair]) for pair in pairs},
        "turnover_one_way_sum": turnover / 2.0,
        "adaptive": _metrics(adaptive_equity, adaptive_returns),
        "equal_weight": _metrics(equal_equity, equal_returns),
        "final_weights": weights,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    _write_cycles(args.output_dir / "cycles.csv", all_cycles)
    with (args.output_dir / "equity_curve.csv").open("w", newline="") as handle:
        fields = list(equity_rows[0])
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(equity_rows)
    _write_report(args.output_dir / "report.md", summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
