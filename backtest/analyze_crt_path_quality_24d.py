#!/usr/bin/env python3
"""Analyze CRT entry-to-target path quality without changing accepted trades."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "backtest/ctrader_volume_data"
SOURCE = ROOT / "backtest/crt_trader_24d_results/feature_analysis/feature_matrix.csv"
OUT = ROOT / "backtest/crt_trader_24d_results/path_quality_analysis"


def load_frames() -> dict[str, pd.DataFrame]:
    frames = {}
    for path in sorted(DATA.glob("*_m5_24d.json")):
        payload = json.loads(path.read_text())
        pair = str(payload.get("pair") or path.name.split("_")[0]).upper()
        frame = pd.DataFrame(payload["candles"])
        frame["time"] = pd.to_datetime(frame["time"], utc=True)
        frames[pair] = frame.sort_values("time").drop_duplicates("time").set_index("time").astype({c: float for c in ["open", "high", "low", "close", "volume"]})
    return frames


def atr(frame: pd.DataFrame, idx: int, window: int = 14) -> float:
    x = frame.iloc[max(0, idx - window):idx]
    value = float((x.high - x.low).median()) if len(x) else 0.0
    return value if value > 0 else max(abs(float(frame.close.iloc[idx])) * 1e-5, 1e-12)


def swings(frame: pd.DataFrame, length: int = 3) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    highs, lows = [], []
    for i in range(length, len(frame) - length):
        high = float(frame.high.iloc[i]); low = float(frame.low.iloc[i])
        if high >= max(float(frame.high.iloc[i-j]) for j in range(1, length+1)) and high > max(float(frame.high.iloc[i+j]) for j in range(1, length+1)):
            highs.append((i, high))
        if low <= min(float(frame.low.iloc[i-j]) for j in range(1, length+1)) and low < min(float(frame.low.iloc[i+j]) for j in range(1, length+1)):
            lows.append((i, low))
    return highs, lows


def fvg_zones(frame: pd.DataFrame) -> list[tuple[int, int, str, float, float]]:
    zones = []
    for i in range(2, len(frame)):
        h0, l0 = float(frame.high.iloc[i-2]), float(frame.low.iloc[i-2])
        h2, l2 = float(frame.high.iloc[i]), float(frame.low.iloc[i])
        if l2 > h0:
            zones.append((i-2, i, "BULLISH_FVG", h0, l2))
        if h2 < l0:
            zones.append((i-2, i, "BEARISH_FVG", h2, l0))
    return zones


def path_features(row: pd.Series, frame: pd.DataFrame, highs, lows, fvgs) -> dict:
    entry = float(row.entry); stop = float(row.stop); target = float(row.target); equilibrium = float(row.equilibrium)
    risk = abs(entry - stop); long = str(row.side).upper() == "LONG"
    entry_idx = frame.index.get_indexer([pd.Timestamp(row.entry_time)])[0]
    exit_idx = frame.index.get_indexer([pd.Timestamp(row.exit_time)])[0]
    if entry_idx < 0: return {}
    exit_idx = len(frame) - 1 if exit_idx < 0 else max(entry_idx, exit_idx)
    direction = 1 if long else -1
    target_distance = abs(target - entry)
    lo, hi = sorted((entry, target))
    path_swings = [(i, p) for i, p in (highs if long else lows) if entry_idx < i <= exit_idx and lo < p < hi]
    path_swings.sort(key=lambda x: x[0])
    obstacles = [x for x in path_swings]
    path_fvgs = [(a, b, kind, zlo, zhi) for a, b, kind, zlo, zhi in fvgs if b > entry_idx and a <= exit_idx and zhi >= lo and zlo <= hi]
    opposing_fvgs = [z for z in path_fvgs if (long and z[2] == "BEARISH_FVG") or ((not long) and z[2] == "BULLISH_FVG")]

    first_eq = None; first_target = None; first_stop = None
    max_fav = 0.0; max_fav_before_eq = 0.0
    for i in range(entry_idx + 1, exit_idx + 1):
        bar = frame.iloc[i]
        favorable = (float(bar.high) - entry) * direction
        max_fav = max(max_fav, favorable)
        if first_eq is None and ((float(bar.high) >= equilibrium) if long else (float(bar.low) <= equilibrium)):
            first_eq = i
        if first_eq is None:
            max_fav_before_eq = max(max_fav_before_eq, favorable)
        if first_target is None and ((float(bar.high) >= target) if long else (float(bar.low) <= target)):
            first_target = i
        if first_stop is None and ((float(bar.low) <= stop) if long else (float(bar.high) >= stop)):
            first_stop = i

    post_n = min(len(frame), entry_idx + 4)
    post = frame.iloc[entry_idx+1:post_n]
    bodies = ((post.close - post.open) * direction / max(risk, 1e-12)).abs()
    aligned_bodies = ((post.close - post.open) * direction / max(risk, 1e-12))
    displacement_3 = float(aligned_bodies.sum()) if len(post) else 0.0
    max_displacement_3 = float(aligned_bodies.max()) if len(post) else 0.0

    # Pre-entry directional alignment: last 24 M5 closes and previous 2H CRT candle body.
    prior = frame.iloc[max(0, entry_idx-24):entry_idx]
    prior_move = (float(prior.close.iloc[-1]) - float(prior.close.iloc[0])) * direction if len(prior) >= 2 else 0.0
    htf_move = (float(row.target) - float(row.equilibrium)) * direction
    htf_alignment = bool(prior_move > 0)

    # Causal structure confirmation: did a close after entry break a pre-entry swing toward target within 6 bars?
    pre_swings = [(i, p) for i, p in (highs if long else lows) if i + 3 <= entry_idx and lo < p < hi]
    structure_bos = False
    for i in range(entry_idx + 1, min(len(frame), entry_idx + 7)):
        close = float(frame.close.iloc[i])
        if long and any(close > p for _, p in pre_swings): structure_bos = True
        if not long and any(close < p for _, p in pre_swings): structure_bos = True

    exit_reason = str(row.exit_reason)
    if exit_reason == "BREAKEVEN": outcome = "EQ_THEN_BE"
    elif exit_reason == "TARGET": outcome = "EQ_THEN_TARGET"
    elif exit_reason == "STOP" and first_eq is None: outcome = "STOP_BEFORE_EQ"
    elif exit_reason == "STOP": outcome = "EQ_THEN_STOP_OR_BE_ORDER"
    else: outcome = "OTHER"

    first_obstacle_atr = abs(obstacles[0][1] - entry) / max(atr(frame, entry_idx), 1e-12) if obstacles else np.nan
    return {
        "outcome_path": outcome,
        "equilibrium_reached_before_exit": bool(first_eq is not None),
        "target_reached_before_exit": bool(first_target is not None),
        "first_equilibrium_bars": first_eq - entry_idx if first_eq is not None else np.nan,
        "max_favorable_excursion_r": max_fav / max(risk, 1e-12),
        "max_favorable_before_equilibrium_r": max_fav_before_eq / max(risk, 1e-12),
        "obstacles_between_entry_target": len(obstacles),
        "first_obstacle_distance_atr": first_obstacle_atr,
        "opposing_fvg_obstacles": len(opposing_fvgs),
        "range_size_atr": abs(float(row.target) - float(row.target)) + abs(float(row.target) - float(row.equilibrium)) * 2 / max(atr(frame, entry_idx), 1e-12),
        "displacement_3bar_risk": displacement_3,
        "max_displacement_3bar_risk": max_displacement_3,
        "htf_directional_alignment": htf_alignment,
        "structure_bos_after_reentry": structure_bos,
        "target_distance_r": abs(target - entry) / max(risk, 1e-12),
        "equilibrium_distance_r": abs(equilibrium - entry) / max(risk, 1e-12),
    }


def main() -> int:
    df = pd.read_csv(SOURCE)
    frames = load_frames()
    out = []
    cache = {}
    for pair, frame in frames.items():
        cache[pair] = (frame, *swings(frame), fvg_zones(frame))
    for _, row in df.iterrows():
        frame, highs, lows, fvgs = cache[row.instrument]
        features = path_features(row, frame, highs, lows, fvgs)
        record = row.to_dict(); record.update(features); out.append(record)
    result = pd.DataFrame(out)
    OUT.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUT / "trade_path_matrix.csv", index=False)

    def medians(group):
        cols = ["target_distance_r", "equilibrium_distance_r", "obstacles_between_entry_target", "first_obstacle_distance_atr", "opposing_fvg_obstacles", "displacement_3bar_risk", "max_displacement_3bar_risk", "max_favorable_excursion_r", "range_size_atr"]
        return {c: round(float(pd.to_numeric(group[c], errors="coerce").median()), 4) if group[c].notna().any() else None for c in cols}

    outcome_counts = result.outcome_path.value_counts(dropna=False).to_dict()
    boolean_rates = {}
    for col in ["htf_directional_alignment", "structure_bos_after_reentry", "equilibrium_reached_before_exit"]:
        boolean_rates[col] = {
            str(name): {"trades": int(len(group)), "true": int(group[col].sum()), "true_pct": round(float(group[col].mean() * 100), 4)}
            for name, group in result.groupby("outcome_path", dropna=False)
        }
    result["displacement_band"] = pd.cut(result.displacement_3bar_risk, [-999, -0.25, 0, 0.5, 1, 999])
    displacement_bands = {
        str(name): {"trades": int(len(group)), "equilibrium_rate_pct": round(float(group.equilibrium_reached_before_exit.mean() * 100), 4), "target_rate_pct": round(float(group.target_reached_before_exit.mean() * 100), 4), "total_r": round(float(group.r_multiple.sum()), 6)}
        for name, group in result.groupby("displacement_band", observed=False, dropna=False)
    }
    regime = {}
    for name, group in result.groupby("volatility_regime", dropna=False):
        regime[str(name)] = {"trades": int(len(group)), "outcomes": group.outcome_path.value_counts().to_dict(), "medians": medians(group)}
    summary = {
        "trades": int(len(result)),
        "outcome_counts": outcome_counts,
        "boolean_rates_by_outcome": boolean_rates,
        "displacement_bands": displacement_bands,
        "overall_medians": medians(result),
        "by_outcome": {str(name): {"trades": int(len(group)), "medians": medians(group)} for name, group in result.groupby("outcome_path", dropna=False)},
        "by_regime": regime,
        "by_session": {str(name): {"trades": int(len(group)), "outcomes": group.outcome_path.value_counts().to_dict()} for name, group in result.groupby("session", dropna=False)},
        "by_side": {str(name): {"trades": int(len(group)), "outcomes": group.outcome_path.value_counts().to_dict()} for name, group in result.groupby("side", dropna=False)},
        "definitions": {
            "obstacles_between_entry_target": "confirmed 3-left/3-right M5 swing pivots strictly between entry and CRT target before the recorded exit",
            "opposing_fvg_obstacles": "simple three-candle FVG zones of opposing polarity intersecting the entry-target path",
            "displacement_3bar_risk": "sum of post-entry aligned candle bodies over first three M5 bars, divided by initial risk",
            "structure_bos_after_reentry": "within six post-entry bars, a close breaks a pre-entry confirmed swing in target direction",
            "htf_directional_alignment": "last 24 M5 closes before entry move in the target direction",
            "path_features": "descriptive diagnostics; they do not alter the accepted trade set",
        },
        "limitations": [
            "Obstacle and FVG counts are causal-path approximations, not a replacement for the full original engine POI objects.",
            "Path diagnostics after entry are intentionally post-entry descriptors and must not be used as entry filters without a new walk-forward design.",
            "OHLC cannot resolve same-bar ordering beyond the conservative exit logic already used by the CRT simulator.",
            "No spread, slippage, bid/ask, or news data are available.",
        ],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=lambda x: int(x) if isinstance(x, np.integer) else float(x) if isinstance(x, np.floating) else x) + "\n")
    lines = ["# CRT entry-to-target path quality (24 days)", "", "> Descriptive analysis only: the 132 accepted trades and their original exits were not changed.", "", "## Outcome split", "", "| Path outcome | Trades |", "|---|---:|"]
    for name, count in outcome_counts.items(): lines.append(f"| {name} | {count} |")
    lines += ["", "## By volatility regime", "", "| Regime | Trades | Outcome counts |", "|---|---:|---|"]
    for name, row in regime.items(): lines.append(f"| {name} | {row['trades']} | `{json.dumps(row['outcomes'], sort_keys=True)}` |")
    lines += ["", "## Feature medians by path outcome", "", "| Outcome | Trades | Target R | Eq R | Obstacles | First obstacle ATR | 3-bar displacement/R | MFE R |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, row in summary["by_outcome"].items():
        m = row["medians"]
        vals = [m.get("target_distance_r"), m.get("equilibrium_distance_r"), m.get("obstacles_between_entry_target"), m.get("first_obstacle_distance_atr"), m.get("displacement_3bar_risk"), m.get("max_favorable_excursion_r")]
        lines.append(f"| {name} | {row['trades']} | {vals[0]} | {vals[1]} | {vals[2]} | {vals[3]} | {vals[4]} | {vals[5]} |")
    lines += ["", "## Confirmation rates by path outcome", "", "| Outcome | HTF alignment | BOS after re-entry | Equilibrium reached |", "|---|---:|---:|---:|"]
    for name in outcome_counts:
        lines.append(f"| {name} | {boolean_rates['htf_directional_alignment'][name]['true_pct']:.2f}% | {boolean_rates['structure_bos_after_reentry'][name]['true_pct']:.2f}% | {boolean_rates['equilibrium_reached_before_exit'][name]['true_pct']:.2f}% |")
    lines += ["", "## Displacement bands", "", "| 3-bar aligned body / initial risk | Trades | Eq reached | Target reached | Total R |", "|---|---:|---:|---:|---:|"]
    for name, row in displacement_bands.items():
        lines.append(f"| {name} | {row['trades']} | {row['equilibrium_rate_pct']:.2f}% | {row['target_rate_pct']:.2f}% | {row['total_r']:.4f} |")
    lines += ["", "## Caveat", "", "The obstacle/FVG/structure metrics are diagnostic approximations aligned with the original engine's concepts. They are not entry rules and were not used to select or remove trades.", ""]
    (OUT / "report.md").write_text("\n".join(lines))
    print(json.dumps(summary, indent=2, default=lambda x: int(x) if isinstance(x, np.integer) else float(x) if isinstance(x, np.floating) else x))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
