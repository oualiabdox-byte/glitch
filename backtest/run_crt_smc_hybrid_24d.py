#!/usr/bin/env python3
"""Non-blocking CRT-SMC hybrid research layer.

CRT remains the signal generator. SMC features are evidence and a soft score;
no trade is rejected. This is deliberately a research artifact, not production.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "backtest/ctrader_volume_data"
SOURCE = ROOT / "backtest/crt_trader_24d_results/path_quality_analysis/trade_path_matrix.csv"
OUT = ROOT / "backtest/crt_trader_24d_results/crt_smc_hybrid"


def load_frames():
    frames = {}
    for path in sorted(DATA.glob("*_m5_24d.json")):
        payload = json.loads(path.read_text())
        pair = str(payload.get("pair") or path.name.split("_")[0]).upper()
        frame = pd.DataFrame(payload["candles"])
        frame["time"] = pd.to_datetime(frame["time"], utc=True)
        frame = frame.sort_values("time").drop_duplicates("time").set_index("time")
        frames[pair] = frame.astype({c: float for c in ["open", "high", "low", "close", "volume"]})
    return frames


def atr(frame, idx, window=14):
    sample = frame.iloc[max(0, idx - window):idx]
    value = float((sample.high - sample.low).median()) if len(sample) else 0.0
    return value if value > 0 else max(abs(float(frame.close.iloc[idx])) * 1e-5, 1e-12)


def causal_pivots(frame, end, length=3):
    highs, lows = [], []
    for i in range(length, max(length, end - length + 1)):
        if i + length >= len(frame):
            break
        hi = float(frame.high.iloc[i]); lo = float(frame.low.iloc[i])
        if hi >= max(float(frame.high.iloc[i-j]) for j in range(1, length + 1)) and hi > max(float(frame.high.iloc[i+j]) for j in range(1, length + 1)):
            highs.append((i, hi))
        if lo <= min(float(frame.low.iloc[i-j]) for j in range(1, length + 1)) and lo < min(float(frame.low.iloc[i+j]) for j in range(1, length + 1)):
            lows.append((i, lo))
    return highs, lows


def fvg_near_entry(frame, entry_idx, side, max_age=18):
    """Causal three-candle FVG formed before entry and still near price."""
    entry = float(frame.close.iloc[entry_idx]); unit = atr(frame, entry_idx)
    for i in range(max(2, entry_idx - max_age), entry_idx):
        h0, l0 = float(frame.high.iloc[i-2]), float(frame.low.iloc[i-2])
        h2, l2 = float(frame.high.iloc[i]), float(frame.low.iloc[i])
        if side == "LONG" and l2 > h0:
            bottom, top, kind = h0, l2, "BULLISH_FVG"
        elif side == "SHORT" and h2 < l0:
            bottom, top, kind = h2, l0, "BEARISH_FVG"
        else:
            continue
        if bottom - unit * 0.5 <= entry <= top + unit * 0.5:
            return True, kind, abs(entry - (bottom + top) / 2) / max(unit, 1e-12)
    return False, "NONE", np.nan


def ob_near_entry(frame, entry_idx, side, max_age=12):
    """Causal approximation: recent opposite-body candle whose zone is near entry."""
    entry = float(frame.close.iloc[entry_idx]); unit = atr(frame, entry_idx)
    for i in range(entry_idx - 1, max(-1, entry_idx - max_age - 1), -1):
        op, cl = float(frame.open.iloc[i]), float(frame.close.iloc[i])
        opposite = (side == "LONG" and cl < op) or (side == "SHORT" and cl > op)
        if not opposite:
            continue
        bottom, top = float(frame.low.iloc[i]), float(frame.high.iloc[i])
        if bottom - unit <= entry <= top + unit:
            return True, abs(entry - (bottom + top) / 2) / max(unit, 1e-12)
    return False, np.nan


def causal_bos_before_entry(frame, entry_idx, side):
    highs, lows = causal_pivots(frame, entry_idx, 3)
    pivots = highs if side == "LONG" else lows
    if not pivots:
        return False
    pivot = pivots[-1][1]
    start = max(0, entry_idx - 6)
    closes = frame.close.iloc[start:entry_idx]
    if side == "LONG":
        return bool((closes > pivot).any())
    return bool((closes < pivot).any())


def pre_entry_displacement(frame, entry_idx, side):
    direction = 1 if side == "LONG" else -1
    recent = frame.iloc[max(0, entry_idx - 3):entry_idx]
    if recent.empty:
        return 0.0
    aligned_body = ((recent.close - recent.open) * direction).sum()
    return float(aligned_body / max(atr(frame, entry_idx), 1e-12))


def score_row(row, frame):
    side = str(row.side).upper()
    entry_idx = frame.index.get_indexer([pd.Timestamp(row.entry_time)])[0]
    if entry_idx < 0:
        return {}
    fvg, fvg_kind, fvg_dist = fvg_near_entry(frame, entry_idx, side)
    ob, ob_dist = ob_near_entry(frame, entry_idx, side)
    bos = causal_bos_before_entry(frame, entry_idx, side)
    pre_disp = pre_entry_displacement(frame, entry_idx, side)
    htf = bool(row.htf_directional_alignment)
    # Soft components: no threshold can reject a trade.
    location = 1.0 if htf else 0.0
    liquidity = min(1.0, max(0.0, float(row.sweep_size_atr) / 1.0))
    structure = 1.0 if bos else 0.0
    displacement = min(1.0, max(0.0, (pre_disp + 0.5) / 1.5))
    poi = (int(fvg) + int(ob)) / 2.0
    score = 100.0 * (0.20 * location + 0.20 * liquidity + 0.20 * structure + 0.20 * displacement + 0.20 * poi)
    if score < 35:
        band = "WEAK"
    elif score < 65:
        band = "BALANCED"
    else:
        band = "STRONG"
    return {
        "smc_htf_alignment": htf,
        "smc_causal_bos_before_entry": bos,
        "smc_pre_entry_displacement_atr": round(pre_disp, 6),
        "smc_fvg_near_entry": fvg,
        "smc_fvg_kind": fvg_kind,
        "smc_fvg_distance_atr": round(float(fvg_dist), 6) if pd.notna(fvg_dist) else np.nan,
        "smc_ob_near_entry": ob,
        "smc_ob_distance_atr": round(float(ob_dist), 6) if pd.notna(ob_dist) else np.nan,
        "smc_soft_score": round(score, 6),
        "smc_quality_band": band,
        "smc_score_location": round(location, 6),
        "smc_score_liquidity": round(liquidity, 6),
        "smc_score_structure": round(structure, 6),
        "smc_score_displacement": round(displacement, 6),
        "smc_score_poi": round(poi, 6),
    }


def metric(group):
    values = pd.to_numeric(group.r_multiple, errors="coerce").dropna()
    wins = values[values > 0]; losses = values[values < 0]
    gross_loss = abs(losses.sum())
    equity = values.cumsum(); drawdown = float((equity.cummax() - equity).max()) if len(values) else 0.0
    return {
        "trades": int(len(values)),
        "win_rate_pct": round(float((values > 0).mean() * 100), 2) if len(values) else 0.0,
        "total_r": round(float(values.sum()), 6),
        "avg_r": round(float(values.mean()), 6) if len(values) else 0.0,
        "profit_factor": round(float(wins.sum() / gross_loss), 6) if gross_loss else None,
        "max_drawdown_r": round(drawdown, 6),
    }


def main():
    frames = load_frames()
    data = pd.read_csv(SOURCE)
    rows = []
    for _, row in data.iterrows():
        record = row.to_dict()
        record.update(score_row(row, frames[str(row.instrument).upper()]))
        rows.append(record)
    result = pd.DataFrame(rows).sort_values("exit_time")
    # Keep all CRT trades: the hybrid is a score/risk layer, not a rejection gate.
    result["soft_risk_multiplier_research"] = result.smc_quality_band.map({"WEAK": 0.75, "BALANCED": 1.0, "STRONG": 1.25}).fillna(1.0)
    result["soft_sized_r_research"] = result.r_multiple * result.soft_risk_multiplier_research
    OUT.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUT / "trade_matrix.csv", index=False)
    by_band = {str(name): metric(group) | {"mean_score": round(float(group.smc_soft_score.mean()), 4)} for name, group in result.groupby("smc_quality_band", sort=False)}
    by_score_bin = {}
    result["score_bin"] = pd.cut(result.smc_soft_score, [-1, 35, 50, 65, 80, 101], right=False)
    for name, group in result.groupby("score_bin", observed=False, dropna=False):
        by_score_bin[str(name)] = metric(group) | {"mean_score": round(float(group.smc_soft_score.mean()), 4) if len(group) else None}
    equal = metric(result)
    sized = metric(result.assign(r_multiple=result.soft_sized_r_research))
    summary = {
        "trades_preserved": int(len(result)),
        "crt_baseline_metrics": equal,
        "soft_sizing_research_metrics": sized,
        "by_quality_band": by_band,
        "by_score_bin": by_score_bin,
        "quality_counts": result.smc_quality_band.value_counts().to_dict(),
        "feature_rates": {
            c: round(float(result[c].mean() * 100), 2)
            for c in ["smc_htf_alignment", "smc_causal_bos_before_entry", "smc_fvg_near_entry", "smc_ob_near_entry"]
        },
        "weights": {"location_htf": 0.20, "liquidity": 0.20, "structure_bos": 0.20, "displacement": 0.20, "poi_fvg_ob": 0.20},
        "policy": "No trade rejection. Score is evidence for ranking, review, and future soft position sizing only.",
        "limitations": [
            "FVG/OB detectors are causal research approximations, not the incomplete production SMC engine.",
            "The score is descriptive and has not been walk-forward validated.",
            "Soft sizing is shown as a research scenario, not a trading recommendation.",
            "No spread, slippage, commission, or news costs are included.",
        ],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=lambda x: int(x) if isinstance(x, np.integer) else float(x) if isinstance(x, np.floating) else x) + "\n")
    lines = ["# CRT-SMC Hybrid Soft Layer — 24 days", "", "> All 132 CRT trades are preserved. SMC evidence creates a quality score; it does not reject trades.", "", "## Overall", "", "| Mode | Trades | Win rate | Total R | Avg R | PF | Max DD R |", "|---|---:|---:|---:|---:|---:|---:|"]
    for name, row in [("CRT baseline / equal risk", equal), ("Research soft sizing", sized)]:
        lines.append(f"| {name} | {row['trades']} | {row['win_rate_pct']:.2f}% | {row['total_r']:.4f} | {row['avg_r']:.4f} | {row['profit_factor']} | {row['max_drawdown_r']:.4f} |")
    lines += ["", "## Quality bands", "", "| Band | Trades | Mean score | Win rate | Total R | PF | Max DD R |", "|---|---:|---:|---:|---:|---:|---:|"]
    for name, row in by_band.items():
        lines.append(f"| {name} | {row['trades']} | {row['mean_score']:.2f} | {row['win_rate_pct']:.2f}% | {row['total_r']:.4f} | {row['profit_factor']} | {row['max_drawdown_r']:.4f} |")
    lines += ["", "## Design", "", "The CRT rules remain the candidate generator. HTF alignment, causal BOS, pre-entry displacement, and nearby FVG/OB evidence are scored softly. A later walk-forward study may use the score for position-size modulation, but not for deleting setups.", "", "## Limitations", "", *[f"- {x}" for x in summary["limitations"]], ""]
    (OUT / "report.md").write_text("\n".join(lines))
    print(json.dumps(summary, indent=2, default=lambda x: int(x) if isinstance(x, np.integer) else float(x) if isinstance(x, np.floating) else x))


if __name__ == "__main__":
    main()
