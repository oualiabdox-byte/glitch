#!/usr/bin/env python3
"""Counterfactual CRT quality-layer experiment.

This script filters already-generated trades only. It does not regenerate signals,
change CRT rules, or use outcomes in the score. Results are research-only.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backtest/crt_trader_24d_results/feature_analysis/feature_matrix.csv"
OUT = ROOT / "backtest/crt_trader_24d_results/soft_score_experiment"


def metrics(frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {"trades": 0, "win_rate_pct": None, "total_r": 0.0, "avg_r": None, "profit_factor": None}
    r = pd.to_numeric(frame.r_multiple, errors="coerce")
    gains = float(r[r > 0].sum())
    losses = float(-r[r < 0].sum())
    return {
        "trades": int(len(frame)),
        "wins": int((r > 0).sum()),
        "losses": int((r < 0).sum()),
        "win_rate_pct": round(float((r > 0).mean() * 100), 4),
        "total_r": round(float(r.sum()), 6),
        "avg_r": round(float(r.mean()), 6),
        "profit_factor": round(gains / losses, 6) if losses else None,
    }


def add_score(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["session_score"] = out.session.map({"overlap": 1.0, "other": 0.4, "london": 0.1, "new_york": 0.1}).fillna(0.4)
    out["regime_score"] = out.volatility_regime.map({"RANGE_CONTRACTION": 1.0, "TRANSITION": 0.5, "TREND_CONTRACTION": 0.5, "RANGE_EXPANSION": 0.1, "TREND_EXPANSION": 0.1}).fillna(0.4)
    out["sweep_score"] = (1.0 - pd.to_numeric(out.sweep_size_atr).clip(lower=0, upper=1.2) / 1.2).clip(0, 1)
    out["stop_score"] = (1.0 - pd.to_numeric(out.stop_distance_atr).clip(lower=0, upper=1.5) / 1.5).clip(0, 1)
    out["reentry_score"] = (1.0 - pd.to_numeric(out.reentry_penetration_atr).clip(lower=0, upper=1.0)).clip(0, 1)
    out["soft_score"] = (
        0.25 * out.session_score
        + 0.25 * out.regime_score
        + 0.20 * out.sweep_score
        + 0.15 * out.stop_score
        + 0.15 * out.reentry_score
    )
    return out


def main() -> int:
    frame = add_score(pd.read_csv(SOURCE))
    OUT.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUT / "scored_feature_matrix.csv", index=False)
    experiments = {
        "raw_crt": frame,
        "overlap_only": frame[frame.session == "overlap"],
        "range_contraction_only": frame[frame.volatility_regime == "RANGE_CONTRACTION"],
        "soft_score_ge_0_60": frame[frame.soft_score >= 0.60],
        "soft_score_ge_0_70": frame[frame.soft_score >= 0.70],
    }
    results = {name: metrics(rows) for name, rows in experiments.items()}
    summary = {
        "source": str(SOURCE),
        "results": results,
        "score_definition": {
            "session": "overlap=1.0, other=0.4, london/new_york=0.1",
            "regime": "range_contraction=1.0, transition/trend_contraction=0.5, expansion=0.1",
            "sweep": "linear preference for sweep_size_atr <= 1.2",
            "stop": "linear preference for stop_distance_atr <= 1.5",
            "reentry": "linear preference for reentry_penetration_atr <= 1.0",
            "weights": "session 25%, regime 25%, sweep 20%, stop 15%, reentry 15%",
        },
        "limitations": [
            "This is a counterfactual over accepted CRT trades, not a full opportunity-recapture test.",
            "The score uses causal entry features only and never uses r_multiple.",
            "The 24-day result is not sufficient to promote any score or threshold to production.",
        ],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = [
        "# CRT soft-score ablation (24 days)",
        "",
        "> Research-only counterfactual. CRT generation, adapter behavior, and trailer behavior were not changed.",
        "",
        "| Experiment | Trades | Win rate | Total R | Avg R | Profit factor |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, row in results.items():
        pf = "n/a" if row["profit_factor"] is None else f"{row['profit_factor']:.4f}"
        wr = "n/a" if row["win_rate_pct"] is None else f"{row['win_rate_pct']:.2f}%"
        avg = "n/a" if row["avg_r"] is None else f"{row['avg_r']:.4f}"
        lines.append(f"| {name} | {row['trades']} | {wr} | {row['total_r']:.4f} | {avg} | {pf} |")
    lines += [
        "",
        "## Interpretation",
        "",
        "The score is an evaluation layer, not a live filter. A positive result here does not measure missed CRT candidates and does not establish robustness.",
        "The next validation must freeze the score definition and test it on a later out-of-sample window.",
        "",
    ]
    (OUT / "report.md").write_text("\n".join(lines))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
