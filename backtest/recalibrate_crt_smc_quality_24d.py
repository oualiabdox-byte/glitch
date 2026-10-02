#!/usr/bin/env python3
"""Walk-forward recalibration of non-blocking CRT-SMC quality bands."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backtest/crt_trader_24d_results/crt_smc_hybrid/trade_matrix.csv"
OUT = ROOT / "backtest/crt_trader_24d_results/crt_smc_recalibration"

LOWER = [25, 30, 35, 40, 45, 50]
UPPER = [50, 55, 60, 65, 70, 75]
MULTIPLIERS = [(0.25, 0.75, 1.0), (0.25, 1.0, 1.0), (0.5, 0.75, 1.0), (0.5, 1.0, 1.0), (0.75, 1.0, 1.0), (0.5, 1.0, 1.25)]


def metrics(values):
    values = pd.Series(values, dtype=float).dropna()
    wins = values[values > 0]; losses = values[values < 0]
    gross_loss = abs(float(losses.sum()))
    equity = values.cumsum(); dd = float((equity.cummax() - equity).max()) if len(values) else 0.0
    return {
        "trades": int(len(values)),
        "total_r": round(float(values.sum()), 6),
        "avg_r": round(float(values.mean()), 6) if len(values) else 0.0,
        "win_rate_pct": round(float((values > 0).mean() * 100), 2) if len(values) else 0.0,
        "profit_factor": round(float(wins.sum() / gross_loss), 6) if gross_loss else None,
        "max_drawdown_r": round(dd, 6),
    }


def assign_band(score, low, high):
    return np.where(score < low, "WEAK", np.where(score < high, "BALANCED", "STRONG"))


def evaluate(frame, low, high, multipliers):
    bands = assign_band(frame.smc_soft_score.to_numpy(), low, high)
    mult = pd.Series(bands, index=frame.index).map({"WEAK": multipliers[0], "BALANCED": multipliers[1], "STRONG": multipliers[2]}).astype(float)
    return frame.r_multiple * mult, bands


def objective(values):
    m = metrics(values)
    # Prefer positive return with drawdown control; do not reward tiny samples
    # because all trades remain present but their risk can be downweighted.
    return float(m["total_r"] / max(m["max_drawdown_r"], 1.0)) + (0.02 if m["total_r"] > 0 else 0.0)


def search(train):
    best = None
    for low in LOWER:
        for high in UPPER:
            if high <= low + 5:
                continue
            for mult in MULTIPLIERS:
                sized, bands = evaluate(train, low, high, mult)
                score = objective(sized)
                candidate = {"low": low, "high": high, "multipliers": mult, "objective": score, "train_metrics": metrics(sized), "train_band_counts": pd.Series(bands).value_counts().to_dict()}
                if best is None or score > best["objective"]:
                    best = candidate
    return best


def main():
    data = pd.read_csv(SOURCE)
    data["entry_time"] = pd.to_datetime(data.entry_time, utc=True)
    data = data.sort_values("entry_time").reset_index(drop=True)
    # Two expanding walk-forward folds. Each test segment is chronologically later.
    cut1 = data.entry_time.iloc[int(len(data) * 0.50)]
    cut2 = data.entry_time.iloc[int(len(data) * 0.75)]
    folds = [("train_first_half_test_second_half", data.entry_time < cut1, data.entry_time >= cut1),
             ("train_first_75_test_last_25", data.entry_time < cut2, data.entry_time >= cut2)]
    results = []
    fold_details = {}
    for name, train_mask, test_mask in folds:
        train = data.loc[train_mask].copy(); test = data.loc[test_mask].copy()
        best = search(train)
        test_sized, test_bands = evaluate(test, best["low"], best["high"], best["multipliers"])
        detail = {
            "train_period": [str(train.entry_time.min()), str(train.entry_time.max())],
            "test_period": [str(test.entry_time.min()), str(test.entry_time.max())],
            "best": best,
            "test_metrics": metrics(test_sized),
            "test_band_counts": pd.Series(test_bands).value_counts().to_dict(),
            "test_unweighted_metrics": metrics(test.r_multiple),
        }
        fold_details[name] = detail
        results.append({"fold": name, "low": best["low"], "high": best["high"], "weak_multiplier": best["multipliers"][0], "balanced_multiplier": best["multipliers"][1], "strong_multiplier": best["multipliers"][2], **{"test_" + k: v for k, v in detail["test_metrics"].items()}})

    # A conservative consensus is the median selected threshold/multipliers,
    # then measured on the full sample only as a descriptive check.
    lows = [v["best"]["low"] for v in fold_details.values()]; highs = [v["best"]["high"] for v in fold_details.values()]
    ms = list(zip(*[v["best"]["multipliers"] for v in fold_details.values()]))
    consensus = {"low": int(np.median(lows)), "high": int(np.median(highs)), "multipliers": tuple(float(np.median(x)) for x in ms)}
    full_sized, full_bands = evaluate(data, consensus["low"], consensus["high"], consensus["multipliers"])
    summary = {
        "trades_preserved": int(len(data)),
        "unweighted_baseline": metrics(data.r_multiple),
        "folds": fold_details,
        "consensus": consensus,
        "consensus_full_sample_descriptive": metrics(full_sized),
        "consensus_band_counts": pd.Series(full_bands).value_counts().to_dict(),
        "interpretation": "Only soft risk allocation changes; no CRT trade is removed. The full-sample consensus result is descriptive, not a validation result.",
        "limitations": [
            "Only 132 trades over 24 days; thresholds are not production settings.",
            "Walk-forward folds are small and use the same limited dataset for research.",
            "The objective can optimize risk allocation, not the underlying trade expectancy; unweighted CRT remains unchanged.",
            "No spread, slippage, commission, or news costs are included.",
        ],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=lambda x: int(x) if isinstance(x, np.integer) else float(x) if isinstance(x, np.floating) else x) + "\n")
    pd.DataFrame(results).to_csv(OUT / "walk_forward_results.csv", index=False)
    # Save full matrix with consensus labels for review.
    labelled = data.copy(); sized, bands = evaluate(labelled, consensus["low"], consensus["high"], consensus["multipliers"])
    labelled["recalibrated_quality_band"] = bands; labelled["recalibrated_risk_multiplier"] = sized / labelled.r_multiple.replace(0, np.nan); labelled["recalibrated_sized_r"] = sized
    labelled.to_csv(OUT / "recalibrated_trade_matrix.csv", index=False)
    lines = ["# CRT-SMC quality recalibration — walk-forward", "", "> All CRT trades remain. Only classification thresholds and soft risk multipliers are recalibrated.", "", "## Baseline", "", f"`{json.dumps(summary['unweighted_baseline'], sort_keys=True)}`", "", "## Walk-forward results", "", "| Fold | Low | High | Weak x | Balanced x | Strong x | Test Total R | Test PF | Test Max DD R |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in results:
        lines.append(f"| {row['fold']} | {row['low']} | {row['high']} | {row['weak_multiplier']} | {row['balanced_multiplier']} | {row['strong_multiplier']} | {row['test_total_r']} | {row['test_profit_factor']} | {row['test_max_drawdown_r']} |")
    lines += ["", "## Consensus", "", f"- Boundaries: `WEAK < {consensus['low']}`, `BALANCED {consensus['low']}–{consensus['high']}`, `STRONG >= {consensus['high']}`.", f"- Multipliers: `WEAK={consensus['multipliers'][0]}`, `BALANCED={consensus['multipliers'][1]}`, `STRONG={consensus['multipliers'][2]}`.", f"- Descriptive full-sample result: `{json.dumps(summary['consensus_full_sample_descriptive'], sort_keys=True)}`.", "", "## Important", "", "A positive soft-sized result would not mean the original CRT expectancy became positive; it means risk was allocated differently across the same trades. The decision must be based on the later walk-forward segments, not the full-sample descriptive result.", "", "## Limitations", "", *[f"- {x}" for x in summary["limitations"]], ""]
    (OUT / "report.md").write_text("\n".join(lines))
    print(json.dumps(summary, indent=2, default=lambda x: int(x) if isinstance(x, np.integer) else float(x) if isinstance(x, np.floating) else x))


if __name__ == "__main__":
    main()
