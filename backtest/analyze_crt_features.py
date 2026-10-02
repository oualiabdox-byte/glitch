#!/usr/bin/env python3
"""Analyze causal CRT feature matrices without changing trade selection."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

FEATURES = [
    "sweep_size_atr", "stop_distance_atr", "target_distance_atr",
    "equilibrium_distance_atr", "entry_body_ratio", "entry_wick_ratio",
    "reentry_penetration_atr", "range_ratio", "volume_ratio",
]


def _stats(frame: pd.DataFrame) -> dict:
    result = {"trades": int(len(frame))}
    if frame.empty:
        return result
    result.update({
        "wins": int((frame.r_multiple > 0).sum()),
        "losses": int((frame.r_multiple < 0).sum()),
        "win_rate_pct": round(float((frame.r_multiple > 0).mean() * 100), 2),
        "total_r": round(float(frame.r_multiple.sum()), 6),
        "avg_r": round(float(frame.r_multiple.mean()), 6),
    })
    for feature in FEATURES:
        values = pd.to_numeric(frame[feature], errors="coerce").dropna()
        if len(values):
            result[f"{feature}_median"] = round(float(values.median()), 6)
            result[f"{feature}_mean"] = round(float(values.mean()), 6)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trades", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    frame = pd.read_csv(args.trades)
    if frame.empty:
        raise SystemExit("trade file is empty")
    required = {"r_multiple", "instrument", "session", "volatility_regime", *FEATURES}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise SystemExit(f"missing feature columns: {', '.join(missing)}")
    frame["outcome"] = frame["r_multiple"].map(lambda value: "WIN" if float(value) > 0 else "LOSS" if float(value) < 0 else "FLAT")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output_dir / "feature_matrix.csv", index=False)

    summary = {
        "source": str(args.trades),
        "trades": int(len(frame)),
        "overall": _stats(frame),
        "by_outcome": {key: _stats(group) for key, group in frame.groupby("outcome", sort=True)},
        "by_pair": {str(key): _stats(group) for key, group in frame.groupby("instrument", sort=True)},
        "by_session": {str(key): _stats(group) for key, group in frame.groupby("session", sort=True)},
        "by_regime": {str(key): _stats(group) for key, group in frame.groupby("volatility_regime", sort=True)},
        "feature_columns": FEATURES,
        "lookahead_policy": "All features are computed from bars available through the CRT entry/re-entry bar; no outcome data is used in feature construction.",
        "research_warning": "Grouping is descriptive only. No threshold or filter is selected from this sample.",
    }
    (args.output_dir / "feature_summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    lines = [
        "# CRT feature archaeology",
        "",
        f"Source: `{args.trades}`",
        "",
        "> This is a descriptive feature matrix. It does not change CRT/TBS entries and does not select a filter.",
        "",
        "## Outcome comparison",
        "",
        "| Group | Trades | Win rate | Total R | Avg R | Sweep ATR median | Stop ATR median | Re-entry ATR median |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key in ("WIN", "LOSS", "FLAT"):
        row = summary["by_outcome"].get(key)
        if not row:
            continue
        lines.append(
            f"| {key} | {row['trades']} | {row.get('win_rate_pct', 0):.2f}% | {row.get('total_r', 0):.4f} | {row.get('avg_r', 0):.4f} | "
            f"{row.get('sweep_size_atr_median', 0):.4f} | {row.get('stop_distance_atr_median', 0):.4f} | {row.get('reentry_penetration_atr_median', 0):.4f} |"
        )
    lines += ["", "## By pair", "", "| Pair | Trades | Win rate | Total R | Avg R |", "|---|---:|---:|---:|---:|"]
    for key, row in summary["by_pair"].items():
        lines.append(f"| {key} | {row['trades']} | {row.get('win_rate_pct', 0):.2f}% | {row.get('total_r', 0):.4f} | {row.get('avg_r', 0):.4f} |")
    lines += ["", "## By volatility regime", "", "| Regime | Trades | Win rate | Total R | Avg R |", "|---|---:|---:|---:|---:|"]
    for key, row in summary["by_regime"].items():
        lines.append(f"| {key} | {row['trades']} | {row.get('win_rate_pct', 0):.2f}% | {row.get('total_r', 0):.4f} | {row.get('avg_r', 0):.4f} |")
    lines += ["", "## By session", "", "| Session | Trades | Win rate | Total R | Avg R |", "|---|---:|---:|---:|---:|"]
    for key, row in summary["by_session"].items():
        lines.append(f"| {key} | {row['trades']} | {row.get('win_rate_pct', 0):.2f}% | {row.get('total_r', 0):.4f} | {row.get('avg_r', 0):.4f} |")
    lines += ["", "## Next step", "", "Freeze any candidate feature hypotheses before testing them on a later out-of-sample window.", ""]
    (args.output_dir / "feature_report.md").write_text("\n".join(lines))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
