#!/usr/bin/env python3
"""Research-only CRT loss-fix ablation on the fixed 24-day fixtures."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "backtest/ctrader_volume_data"
SOURCE = ROOT / "backtest/crt_trader_24d_results/feature_analysis/feature_matrix.csv"
OUT = ROOT / "backtest/crt_trader_24d_results/loss_fix_ablation"


def metrics(values: pd.Series) -> dict:
    values = pd.to_numeric(values, errors="coerce").dropna()
    if values.empty:
        return {"trades": 0, "wins": 0, "losses": 0, "win_rate_pct": None, "total_r": 0.0, "avg_r": None, "profit_factor": None}
    wins = values[values > 0]
    losses = values[values < 0]
    return {
        "trades": int(len(values)),
        "wins": int(len(wins)),
        "losses": int(len(losses)),
        "win_rate_pct": round(float((values > 0).mean() * 100), 4),
        "total_r": round(float(values.sum()), 6),
        "avg_r": round(float(values.mean()), 6),
        "profit_factor": round(float(wins.sum() / abs(losses.sum())), 6) if len(losses) else None,
    }


def load_frames() -> dict[str, pd.DataFrame]:
    frames = {}
    for path in sorted(DATA.glob("*_m5_24d.json")):
        payload = json.loads(path.read_text())
        pair = str(payload.get("pair") or path.name.split("_")[0]).upper()
        frame = pd.DataFrame(payload["candles"])
        frame["time"] = pd.to_datetime(frame["time"], utc=True)
        frames[pair] = frame.sort_values("time").drop_duplicates("time").set_index("time")
    return frames


def equilibrium_r(row: pd.Series, frames: dict[str, pd.DataFrame]) -> float:
    """First-touch equilibrium exit, conservative if stop and target share a bar."""
    frame = frames[row.instrument]
    entry_time = pd.Timestamp(row.entry_time)
    entry_idx = frame.index.get_indexer([entry_time])[0]
    if entry_idx < 0:
        return float(row.r_multiple)
    stop = float(row.stop)
    entry = float(row.entry)
    equilibrium = float(row.equilibrium)
    risk = abs(entry - stop)
    if risk <= 0:
        return float(row.r_multiple)
    long = str(row.side).upper() == "LONG"
    for i in range(entry_idx, len(frame)):
        bar = frame.iloc[i]
        hit_stop = float(bar.low) <= stop if long else float(bar.high) >= stop
        hit_eq = float(bar.high) >= equilibrium if long else float(bar.low) <= equilibrium
        if hit_stop:
            return -1.0
        if hit_eq:
            return abs(equilibrium - entry) / risk
    return -1.0


def main() -> int:
    frame = pd.read_csv(SOURCE, parse_dates=["entry_time"])
    frames = load_frames()
    frame["equilibrium_r"] = frame.apply(lambda row: equilibrium_r(row, frames), axis=1)
    frame["equilibrium_hit"] = frame.equilibrium_r > 0
    OUT.mkdir(parents=True, exist_ok=True)

    experiments = {
        "raw_current_exit": frame,
        "long_only": frame[frame.side == "LONG"],
        "short_only": frame[frame.side == "SHORT"],
        "overlap_only": frame[frame.session == "overlap"],
        "long_overlap": frame[(frame.side == "LONG") & (frame.session == "overlap")],
        "non_expansion": frame[frame.volatility_regime != "RANGE_EXPANSION"],
        "equilibrium_exit_all": frame.assign(r_multiple=frame.equilibrium_r),
        "equilibrium_exit_overlap": frame[frame.session == "overlap"].assign(r_multiple=lambda x: x.equilibrium_r),
        "equilibrium_exit_long": frame[frame.side == "LONG"].assign(r_multiple=lambda x: x.equilibrium_r),
    }
    results = {name: metrics(rows.r_multiple) for name, rows in experiments.items()}
    pair_results = {str(pair): metrics(group.r_multiple) for pair, group in frame.groupby("instrument", sort=True)}
    pair_equilibrium = {str(pair): metrics(group.equilibrium_r) for pair, group in frame.groupby("instrument", sort=True)}
    frame.to_csv(OUT / "trade_matrix_with_equilibrium_exit.csv", index=False)
    summary = {
        "source": str(SOURCE),
        "results": results,
        "pair_current_exit": pair_results,
        "pair_equilibrium_exit": pair_equilibrium,
        "equilibrium_hit_rate_pct": round(float(frame.equilibrium_hit.mean() * 100), 4),
        "definitions": {
            "long_only": "side == LONG",
            "short_only": "side == SHORT",
            "overlap_only": "session == overlap",
            "long_overlap": "side == LONG and session == overlap",
            "non_expansion": "volatility_regime != RANGE_EXPANSION",
            "equilibrium_exit": "first causal bar whose OHLC reaches equilibrium; if stop and equilibrium share a bar, stop is counted first",
        },
        "limitations": [
            "Filters are counterfactual over already accepted CRT trades and do not recover rejected opportunities.",
            "Equilibrium simulation uses OHLC and is conservative on same-bar stop/target ambiguity.",
            "No spread, slippage, news, or bid/ask data are present in the fixtures.",
            "No configuration is promoted to live execution by this experiment.",
        ],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = [
        "# CRT raw loss-fix ablation (24 days)",
        "",
        "> Research-only. CRT generation, adapter behavior, and trailer behavior were not changed.",
        "",
        "| Experiment | Trades | Win rate | Total R | Avg R | PF |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, row in results.items():
        wr = "n/a" if row["win_rate_pct"] is None else f"{row['win_rate_pct']:.2f}%"
        avg = "n/a" if row["avg_r"] is None else f"{row['avg_r']:.4f}"
        pf = "n/a" if row["profit_factor"] is None else f"{row['profit_factor']:.4f}"
        lines.append(f"| {name} | {row['trades']} | {wr} | {row['total_r']:.4f} | {avg} | {pf} |")
    lines += ["", "## Pair breakdown — current exit", "", "| Pair | Trades | Win rate | Total R | PF |", "|---|---:|---:|---:|---:|"]
    for pair, row in pair_results.items():
        pf = "n/a" if row["profit_factor"] is None else f"{row['profit_factor']:.4f}"
        lines.append(f"| {pair} | {row['trades']} | {row['win_rate_pct']:.2f}% | {row['total_r']:.4f} | {pf} |")
    lines += ["", "## Interpretation", "", "Direction and session filters are selection hypotheses. Equilibrium exit is a separate exit experiment and must be compared with realistic spread/slippage before any promotion.", ""]
    (OUT / "report.md").write_text("\n".join(lines))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
