#!/usr/bin/env python3
"""Compare CRT-native alternative engines on the fixed 24-day trade matrix.

These are deliberately simple, causal, and independent of the original SMC
engine. The comparison is descriptive/counterfactual over generated CRT trades;
it is not a production validation.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backtest/crt_trader_24d_results/feature_analysis/feature_matrix.csv"
OUT = ROOT / "backtest/crt_trader_24d_results/native_engines_experiment"


def metrics(frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {"trades": 0, "wins": 0, "losses": 0, "win_rate_pct": None, "total_r": 0.0, "avg_r": None, "profit_factor": None}
    r = pd.to_numeric(frame.r_multiple, errors="coerce")
    gross_win = float(r[r > 0].sum())
    gross_loss = float(-r[r < 0].sum())
    return {
        "trades": int(len(frame)),
        "wins": int((r > 0).sum()),
        "losses": int((r < 0).sum()),
        "win_rate_pct": round(float((r > 0).mean() * 100), 4),
        "total_r": round(float(r.sum()), 6),
        "avg_r": round(float(r.mean()), 6),
        "profit_factor": round(gross_win / gross_loss, 6) if gross_loss else None,
    }


def engines(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    overlap = frame.session == "overlap"
    contraction = frame.volatility_regime == "RANGE_CONTRACTION"
    stable_regime = frame.volatility_regime.isin(["RANGE_CONTRACTION", "TRANSITION", "TREND_CONTRACTION"])
    small_sweep = frame.sweep_size_atr <= 0.60
    controlled_stop = frame.stop_distance_atr <= 1.20
    shallow_reentry = frame.reentry_penetration_atr <= 0.50
    strong_body = frame.entry_body_ratio >= 0.50
    low_wick = frame.entry_wick_ratio <= 0.50
    return {
        "crt_raw": frame,
        "session_liquidity_overlap": frame[overlap],
        "volatility_compression": frame[contraction],
        "sweep_risk_normalization": frame[small_sweep & controlled_stop],
        "reentry_momentum": frame[shallow_reentry & strong_body & low_wick],
        "overlap_sweep_confirmation": frame[overlap & small_sweep & controlled_stop],
        "compression_sweep_confirmation": frame[stable_regime & small_sweep & controlled_stop],
        "overlap_reentry_momentum": frame[overlap & shallow_reentry & strong_body & low_wick],
    }


def main() -> int:
    frame = pd.read_csv(SOURCE)
    result_frames = engines(frame)
    results = {name: metrics(rows) for name, rows in result_frames.items()}
    OUT.mkdir(parents=True, exist_ok=True)
    scored = frame.copy()
    for name, rows in result_frames.items():
        if name == "crt_raw":
            continue
        scored[name] = scored.index.isin(rows.index)
    scored.to_csv(OUT / "engine_membership_matrix.csv", index=False)
    summary = {
        "source": str(SOURCE),
        "results": results,
        "engine_definitions": {
            "session_liquidity_overlap": "session == overlap",
            "volatility_compression": "volatility_regime == RANGE_CONTRACTION",
            "sweep_risk_normalization": "sweep_size_atr <= 0.60 and stop_distance_atr <= 1.20",
            "reentry_momentum": "reentry_penetration_atr <= 0.50 and entry_body_ratio >= 0.50 and entry_wick_ratio <= 0.50",
            "overlap_sweep_confirmation": "overlap plus sweep/stop normalization",
            "compression_sweep_confirmation": "stable non-expansion regime plus sweep/stop normalization",
            "overlap_reentry_momentum": "overlap plus shallow re-entry and body/wick confirmation",
        },
        "limitations": [
            "These engines are tested over already accepted CRT trades; rejected opportunities are not recovered.",
            "Thresholds are research hypotheses and must be frozen before out-of-sample testing.",
            "No engine changes the adapter, trailer, or live execution path.",
        ],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = [
        "# CRT-native alternative engines (24 days)",
        "",
        "> Research-only comparison. These engines do not use the original SMC engine and do not modify CRT generation.",
        "",
        "| Engine | Trades | Win rate | Total R | Avg R | Profit factor |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, row in results.items():
        wr = "n/a" if row["win_rate_pct"] is None else f"{row['win_rate_pct']:.2f}%"
        avg = "n/a" if row["avg_r"] is None else f"{row['avg_r']:.4f}"
        pf = "n/a" if row["profit_factor"] is None else f"{row['profit_factor']:.4f}"
        lines.append(f"| {name} | {row['trades']} | {wr} | {row['total_r']:.4f} | {avg} | {pf} |")
    lines += [
        "",
        "## Recommendation for next validation",
        "",
        "Freeze the best two candidates by mechanism, not by total R alone, then run both on a later out-of-sample period.",
        "Do not combine all conditions yet: very small samples can create an attractive but unstable result.",
        "",
    ]
    (OUT / "report.md").write_text("\n".join(lines))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
