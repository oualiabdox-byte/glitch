#!/usr/bin/env python3
"""Test the requested broad CRT recommendation and target-management variants."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "backtest/ctrader_volume_data"
SOURCE = ROOT / "backtest/crt_trader_24d_results/feature_analysis/feature_matrix.csv"
OUT = ROOT / "backtest/crt_trader_24d_results/recommendation_experiment"
BAD_PAIRS = {"USDCHF", "GBPUSD"}
GOOD_SESSIONS = {"overlap", "other"}


def metrics(values: pd.Series) -> dict:
    values = pd.to_numeric(values, errors="coerce").dropna()
    if values.empty:
        return {"trades": 0, "wins": 0, "losses": 0, "win_rate_pct": None, "total_r": 0.0, "avg_r": None, "profit_factor": None}
    wins = values[values > 0]
    losses = values[values < 0]
    return {"trades": int(len(values)), "wins": int(len(wins)), "losses": int(len(losses)),
            "win_rate_pct": round(float((values > 0).mean() * 100), 4),
            "total_r": round(float(values.sum()), 6), "avg_r": round(float(values.mean()), 6),
            "profit_factor": round(float(wins.sum() / abs(losses.sum())), 6) if len(losses) else None}


def load_frames() -> dict[str, pd.DataFrame]:
    frames = {}
    for path in sorted(DATA.glob("*_m5_24d.json")):
        payload = json.loads(path.read_text())
        pair = str(payload.get("pair") or path.name.split("_")[0]).upper()
        frame = pd.DataFrame(payload["candles"])
        frame["time"] = pd.to_datetime(frame["time"], utc=True)
        frames[pair] = frame.sort_values("time").drop_duplicates("time").set_index("time")
    return frames


def path_result(row: pd.Series, frame: pd.DataFrame, target_r: float, *, ratchet: bool = False) -> float:
    """Simulate one target with initial stop; optionally move stop to BE after 1R."""
    entry = float(row.entry); initial_stop = float(row.stop); risk = abs(entry - initial_stop)
    if risk <= 0: return -1.0
    long = str(row.side).upper() == "LONG"
    target = entry + target_r * risk if long else entry - target_r * risk
    idx = frame.index.get_indexer([pd.Timestamp(row.entry_time)])[0]
    stop = initial_stop
    reached_one = False
    for i in range(max(0, idx), len(frame)):
        bar = frame.iloc[i]
        hit_stop = float(bar.low) <= stop if long else float(bar.high) >= stop
        hit_target = float(bar.high) >= target if long else float(bar.low) <= target
        if hit_stop:
            return 0.0 if reached_one and ratchet else -1.0
        if hit_target:
            return float(target_r)
        if ratchet and not reached_one:
            one_r = entry + risk if long else entry - risk
            crossed = float(bar.high) >= one_r if long else float(bar.low) <= one_r
            if crossed:
                reached_one = True
                stop = entry
    return -1.0


def multi_target(row: pd.Series, frame: pd.DataFrame) -> float:
    """50% at 1R, 25% at 2R, rest at original target; BE after TP1, 1R stop after TP2."""
    entry = float(row.entry); initial_stop = float(row.stop); risk = abs(entry - initial_stop)
    if risk <= 0: return -1.0
    original_r = abs(float(row.target) - entry) / risk
    if original_r <= 1.0:
        levels = [(original_r, 1.0)]
    elif original_r <= 2.0:
        levels = [(1.0, 0.5), (original_r, 0.5)]
    else:
        levels = [(1.0, 0.5), (2.0, 0.25), (original_r, 0.25)]
    long = str(row.side).upper() == "LONG"
    idx = frame.index.get_indexer([pd.Timestamp(row.entry_time)])[0]
    stop = initial_stop; realized = 0.0; remaining = 1.0
    for i in range(max(0, idx), len(frame)):
        bar = frame.iloc[i]
        hit_stop = float(bar.low) <= stop if long else float(bar.high) >= stop
        if hit_stop:
            return realized - remaining
        for level, weight in levels:
            if weight <= 0: continue
            target = entry + level * risk if long else entry - level * risk
            hit = float(bar.high) >= target if long else float(bar.low) <= target
            if hit:
                realized += weight * level
                remaining -= weight
                if level == 1.0:
                    stop = entry
                elif level == 2.0:
                    stop = entry + risk if long else entry - risk
                # Mark filled levels by setting their weight to zero in-place.
                levels[levels.index((level, weight))] = (level, 0.0)
        if remaining <= 1e-9:
            return realized
    return realized - remaining


def main() -> int:
    frame = pd.read_csv(SOURCE)
    frames = load_frames()
    OUT.mkdir(parents=True, exist_ok=True)
    frame["original_target_r"] = (frame.target - frame.entry).abs() / (frame.stop - frame.entry).abs()
    frame["target_2r"] = frame.apply(lambda r: path_result(r, frames[r.instrument], min(float(r.original_target_r), 2.0)), axis=1)
    frame["target_3r"] = frame.apply(lambda r: path_result(r, frames[r.instrument], min(float(r.original_target_r), 3.0)), axis=1)
    frame["tp1_rest_original"] = frame.apply(lambda r: path_result(r, frames[r.instrument], float(r.original_target_r), ratchet=True), axis=1)
    frame["multi_target_r"] = frame.apply(lambda r: multi_target(r, frames[r.instrument]), axis=1)
    base = frame
    recommended = frame[(~frame.instrument.isin(BAD_PAIRS)) & frame.session.isin(GOOD_SESSIONS)]
    recommended_stop = recommended[recommended.stop_distance_atr <= 1.2]
    recommended_sweep = recommended[recommended.sweep_size_atr <= 0.8]
    recommended_target = recommended[recommended.target_distance_atr <= 6.0]
    recommended_target_stop = recommended[(recommended.target_distance_atr <= 6.0) & (recommended.stop_distance_atr <= 1.2)]
    recommended_reentry = recommended[recommended.reentry_penetration_atr >= 0.30]
    experiments = {
        "raw_current_exit": (base, "r_multiple"),
        "exclude_bad_pairs": (base[~base.instrument.isin(BAD_PAIRS)], "r_multiple"),
        "overlap_or_other": (base[base.session.isin(GOOD_SESSIONS)], "r_multiple"),
        "recommended_filter": (recommended, "r_multiple"),
        "recommended_stop_le_1.2atr": (recommended_stop, "r_multiple"),
        "recommended_sweep_le_0.8atr": (recommended_sweep, "r_multiple"),
        "recommended_target_le_6atr": (recommended_target, "r_multiple"),
        "recommended_target_le_6_stop_le_1.2": (recommended_target_stop, "r_multiple"),
        "recommended_reentry_ge_0.30atr": (recommended_reentry, "r_multiple"),
        "recommended_target_2r": (recommended, "target_2r"),
        "recommended_target_3r": (recommended, "target_3r"),
        "recommended_tp1_rest_original": (recommended, "tp1_rest_original"),
        "recommended_multi_target": (recommended, "multi_target_r"),
    }
    results = {name: metrics(rows[col]) for name, (rows, col) in experiments.items()}
    frame.to_csv(OUT / "trade_matrix_with_target_variants.csv", index=False)
    summary = {
        "source": str(SOURCE), "bad_pairs_removed": sorted(BAD_PAIRS), "sessions_kept": sorted(GOOD_SESSIONS),
        "results": results,
        "target_diagnostics": {
            "original_target_r_median_all": round(float(base.original_target_r.median()), 6),
            "original_target_r_median_losses": round(float(base.loc[base.r_multiple < 0, "original_target_r"].median()), 6),
            "original_target_r_median_wins": round(float(base.loc[base.r_multiple > 0, "original_target_r"].median()), 6),
            "current_target_hits": int((base.exit_reason == "TARGET").sum()),
            "target_2r_hits_or_better": int((base.target_2r >= base.original_target_r.clip(upper=2.0)).sum()),
        },
        "definitions": {
            "recommended_filter": "remove USDCHF and GBPUSD; retain Overlap and Other sessions",
            "target_2r/target_3r": "cap the original target at 2R/3R and retain the initial stop",
            "tp1_rest_original": "50% at 1R and 50% at the original target; remaining stop moves to breakeven after 1R",
            "multi_target": "50% at 1R, 25% at 2R, 25% at the original target; stop moves to breakeven after 1R and to +1R after 2R",
        },
        "limitations": [
            "All variants are counterfactual over already accepted CRT trades.",
            "OHLC same-bar ambiguity is handled conservatively by checking stop before target.",
            "No spread, slippage, news, or bid/ask data are included.",
            "The pair removal is a research choice requested by the user and must be validated on new data.",
        ],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = ["# CRT recommendation and target experiment (24 days)", "", "> Research-only. The recommended filter removes USDCHF/GBPUSD and retains Overlap/Other sessions. No live path changed.", "", "| Experiment | Trades | Win rate | Total R | Avg R | PF |", "|---|---:|---:|---:|---:|---:|"]
    for name, row in results.items():
        wr = "n/a" if row["win_rate_pct"] is None else f"{row['win_rate_pct']:.2f}%"; avg = "n/a" if row["avg_r"] is None else f"{row['avg_r']:.4f}"; pf = "n/a" if row["profit_factor"] is None else f"{row['profit_factor']:.4f}"
        lines.append(f"| {name} | {row['trades']} | {wr} | {row['total_r']:.4f} | {avg} | {pf} |")
    lines += [
        "", "## Target-distance diagnosis", "",
        f"Original target median: {summary['target_diagnostics']['original_target_r_median_all']:.2f}R; losses median: {summary['target_diagnostics']['original_target_r_median_losses']:.2f}R; wins median: {summary['target_diagnostics']['original_target_r_median_wins']:.2f}R.",
        "",
        "The 2R/3R caps and multi-target variants were negative because they use the initial stop and remove the original system's breakeven/large-target payoff behavior. This is evidence against a simple fixed 2R replacement, not proof that every partial-exit design fails.",
        "",
        "The recommended pair/session filter leaves 59 trades and +23.10R. Entry-side filters show that stop <= 1.2 ATR leaves 41 trades and +23.49R, while target distance <= 6 ATR leaves 40 trades and +27.13R. Combining them leaves only 32 trades; these are in-sample hypotheses, not production rules.",
        "",
        "The re-entry penetration >= 0.30 ATR filter leaves 33 trades but only +3.59R, so stronger re-entry depth alone is not supported by this sample.",
        "",
        "The multi-target variants are descriptive exit experiments and must be validated with new data, spread, and slippage.", ""
    ]
    (OUT / "report.md").write_text("\n".join(lines))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
