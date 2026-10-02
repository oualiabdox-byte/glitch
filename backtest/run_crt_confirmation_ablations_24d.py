#!/usr/bin/env python3
"""Research-only CRT confirmation ablations on the fixed cTrader 24-day fixtures."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest.crt_tbs_14d import body_tbs_candidates, complete_bars, htf_purges, simulate_trade
from backtest.crt_trader_14d import load_frame, metrics

DATA = ROOT / "backtest/ctrader_volume_data"
OUT = ROOT / "backtest/crt_trader_24d_results/confirmation_ablations"

VARIANTS = {
    "baseline": {},
    "confirm_2_closes": {"confirm_bars": 2},
    "confirm_3_closes": {"confirm_bars": 3},
    "sweep_depth_5pct": {"min_sweep_range_pct": 0.05},
    "sweep_depth_10pct": {"min_sweep_range_pct": 0.10},
    "body_ratio_0.30": {"min_body_ratio": 0.30},
    "body_ratio_0.50": {"min_body_ratio": 0.50},
    "displacement_0.50_atr": {"min_displacement_atr": 0.50},
    "bos_after_reentry": {"require_bos": True},
    "sweep5_body30": {"min_sweep_range_pct": 0.05, "min_body_ratio": 0.30},
    "sweep5_body50": {"min_sweep_range_pct": 0.05, "min_body_ratio": 0.50},
    "sweep5_confirm2": {"min_sweep_range_pct": 0.05, "confirm_bars": 2},
}


def atr(frame: pd.DataFrame, end: int, window: int = 14) -> float:
    x = frame.iloc[max(0, end - window):end]
    value = float((x.high - x.low).median()) if len(x) else 0.0
    return value if value > 0 else max(abs(float(frame.close.iloc[end])) * 1e-5, 1e-12)


def confirmed_pivots(frame: pd.DataFrame, end: int, length: int = 3):
    highs, lows = [], []
    for i in range(length, min(end - length, len(frame) - length)):
        hi = float(frame.high.iloc[i]); lo = float(frame.low.iloc[i])
        if hi >= max(float(frame.high.iloc[i-j]) for j in range(1, length+1)) and hi > max(float(frame.high.iloc[i+j]) for j in range(1, length+1)):
            highs.append((i, hi))
        if lo <= min(float(frame.low.iloc[i-j]) for j in range(1, length+1)) and lo < min(float(frame.low.iloc[i+j]) for j in range(1, length+1)):
            lows.append((i, lo))
    return highs, lows


def adjust_candidate(frame: pd.DataFrame, base: dict[str, Any], side: str, purge: dict[str, Any], options: dict[str, Any]) -> dict[str, Any] | None:
    c = dict(base)
    e = int(c["entry"])
    direction = 1 if side == "LONG" else -1
    level = float(c["level"])
    range_size = max(float(purge["range_high"]) - float(purge["range_low"]), 1e-12)
    sweep_depth = abs(float(c["sweep_extreme"]) - level) / range_size
    if sweep_depth < float(options.get("min_sweep_range_pct", 0.0)):
        return None

    confirm_bars = int(options.get("confirm_bars", 1))
    if confirm_bars > 1:
        last = e + confirm_bars - 1
        if last >= len(frame):
            return None
        closes = [float(frame.close.iloc[i]) for i in range(e, last + 1)]
        if not all((close > level if side == "LONG" else close < level) for close in closes):
            return None
        e = last

    if options.get("min_displacement_atr") is not None:
        last = e + 2
        if last >= len(frame):
            return None
        move = (float(frame.close.iloc[last]) - float(frame.close.iloc[e])) * direction
        if move / max(atr(frame, e), 1e-12) < float(options["min_displacement_atr"]):
            return None
        e = last

    if options.get("require_bos"):
        highs, lows = confirmed_pivots(frame, e, 3)
        pivots = [(i, p) for i, p in (highs if side == "LONG" else lows) if i + 3 <= e]
        if not pivots:
            return None
        pivot = pivots[-1][1]
        bos_i = None
        for i in range(e, min(len(frame), e + 7)):
            close = float(frame.close.iloc[i])
            if (side == "LONG" and close > pivot) or (side == "SHORT" and close < pivot):
                bos_i = i
                break
        if bos_i is None:
            return None
        e = bos_i

    c["entry"] = e
    return c


def run_variant(name: str, options: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    all_trades: list[dict[str, Any]] = []
    diag = {"purges": 0, "base_candidates": 0, "variant_candidates": 0, "trades": 0, "rejected_variant": 0}
    for path in sorted(DATA.glob("*_m5_24d.json")):
        payload = json.loads(path.read_text())
        pair = str(payload.get("pair") or path.name.split("_")[0]).upper()
        frame = load_frame(path)
        m5, htf = complete_bars(frame)
        purges = htf_purges(m5, htf)
        diag["purges"] += len(purges)
        for bucket, purge in purges.items():
            pos = htf.index.get_loc(bucket)
            if pos + 1 >= len(htf):
                continue
            start = int(m5.index.searchsorted(bucket)); end = int(m5.index.searchsorted(htf.index[pos + 1]))
            if end <= start + 8:
                continue
            candidates = body_tbs_candidates(m5, start, end, purge["side"])
            diag["base_candidates"] += len(candidates)
            selected = None
            # Preserve the canonical adapter's selection rule: only the
            # earliest candidate is eligible; a filter may reject it but must
            # not silently promote a later candidate in the same window.
            for base in candidates[:1]:
                candidate = adjust_candidate(m5, base, purge["side"], purge, options)
                if candidate is None:
                    continue
                trade = simulate_trade(m5, candidate, purge["side"], purge, purge["purge_time"])
                if trade is None:
                    continue
                if options.get("min_body_ratio") is not None and trade.entry_body_ratio < float(options["min_body_ratio"]):
                    continue
                selected = trade
                break
            if selected is None:
                diag["rejected_variant"] += 1
                continue
            diag["variant_candidates"] += 1
            row = selected.__dict__.copy()
            row.update({"instrument": pair, "symbol": pair, "variant": name, "source_file": path.name})
            all_trades.append(row)
            diag["trades"] += 1
    return all_trades, diag


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    matrix = []
    all_rows = []
    diagnostics = {}
    for name, options in VARIANTS.items():
        rows, diag = run_variant(name, options)
        result = metrics(sorted(rows, key=lambda row: row["exit_time"]))
        result["variant"] = name
        result["settings"] = options
        matrix.append(result)
        diagnostics[name] = diag
        all_rows.extend(rows)
    pd.DataFrame(matrix).to_csv(OUT / "variant_metrics.csv", index=False)
    pd.DataFrame(all_rows).to_csv(OUT / "variant_trades.csv", index=False)
    summary = {"baseline_trade_count": matrix[0]["trades"], "variants": matrix, "diagnostics": diagnostics, "limitations": [
        "Research-only ablation; no live or production strategy files were changed.",
        "Confirmation/displacement/BOS variants delay entry and therefore are not directly comparable to the original entry price without execution-cost modeling.",
        "OHLC data cannot resolve intrabar ordering; spread, slippage, commission, and news are absent.",
        "The BOS test uses causal 3-bar confirmed pivots and is an approximation of the original structure engine.",
    ]}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    lines = ["# CRT confirmation ablations — 24-day cTrader fixtures", "", "> Research-only variants. The canonical CRT implementation was not changed.", "", "| Variant | Trades | Win rate | Total R | Avg R | Profit factor | Max DD R |", "|---|---:|---:|---:|---:|---:|---:|"]
    for row in matrix:
        lines.append(f"| {row['variant']} | {row['trades']} | {row['win_rate_pct']:.2f}% | {row['total_r']:.4f} | {row['avg_r']:.4f} | {row['profit_factor']} | {row['max_drawdown_r']:.4f} |")
    lines += ["", "## Interpretation", "", "- `confirm_2_closes` and `confirm_3_closes` require consecutive closes back inside the swept level and delay entry to the last confirming close.", "- `sweep_depth_*` measures the M5 sweep distance as a fraction of the parent CRT range.", "- `body_ratio_*` filters the selected entry candle by body/range.", "- `displacement_0.50_atr` waits for a two-bar move of at least 0.50 ATR in the target direction.", "- `bos_after_reentry` waits for a close through a causally confirmed opposing pivot.", "", "## Caveats", "", *[f"- {x}" for x in summary["limitations"]], ""]
    (OUT / "report.md").write_text("\n".join(lines))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
