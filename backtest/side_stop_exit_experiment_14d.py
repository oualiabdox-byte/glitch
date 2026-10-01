#!/usr/bin/env python3
"""Side-only 14d stop/exit experiment; does not alter the production engine.

Signals come from the archived 14d candidate cache so signal generation is held
constant while stop buffers and overnight policy are varied independently.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "backtest" / "ctrader_volume_data"
CACHE = ROOT / "backtest" / "ablation_14d_bos_after_choch" / "signal_cache.json"
OUT = ROOT / "backtest" / "side_stop_exit_14d"
PAIRS = ("AUDUSD", "EURUSD", "GBPUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY")
PIP = 0.0001
ROUND_TURN_COST_PIPS = 1.5
BUFFER_PIPS = (0.0, 0.5, 1.0, 1.5)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_frame(pair: str) -> pd.DataFrame:
    payload = json.loads((DATA / f"{pair}_m5_14d.json").read_text())
    frame = pd.DataFrame(payload["candles"])
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    return frame.sort_values("time").drop_duplicates("time").set_index("time")


def stop_for(signal: dict, buffer_pips: float) -> float:
    evidence = signal.get("evidence", {})
    stop = evidence.get("stop", {})
    anchor = stop.get("anchor")
    if anchor is None:
        anchor = float(signal["stop"])
    delta = buffer_pips * PIP
    return float(anchor) - delta if signal["side"] == "LONG" else float(anchor) + delta


def simulate(signal: dict, frame: pd.DataFrame, buffer_pips: float,
             allow_overnight: bool) -> dict | None:
    signal_close = pd.Timestamp(signal["signal_close_utc"])
    entry_pos = frame.index.searchsorted(signal_close, side="left")
    if entry_pos >= len(frame):
        return None
    entry_bar = frame.iloc[entry_pos]
    fill = float(entry_bar["open"])
    side = 1 if signal["side"] == "LONG" else -1
    stop = stop_for(signal, buffer_pips)
    target = float(signal["target"])
    if (side == 1 and not stop < fill < target) or (side == -1 and not target < fill < stop):
        return {"status": "INVALID_FILL", "entry_time_utc": frame.index[entry_pos].isoformat()}
    risk = abs(fill - stop)
    fill_rr = side * (target - fill) / risk if risk else 0.0
    entry_date = frame.index[entry_pos].date()
    exit_price = float(frame.iloc[-1]["close"])
    exit_reason = "end_of_sample_mark"
    exit_pos = len(frame) - 1
    for pos in range(entry_pos, len(frame)):
        ts = frame.index[pos]
        bar = frame.iloc[pos]
        if not allow_overnight and ts.date() != entry_date:
            exit_price = float(bar["open"])
            exit_reason = "overnight_close"
            exit_pos = pos
            break
        opened, high, low = float(bar["open"]), float(bar["high"]), float(bar["low"])
        if side == 1:
            if opened <= stop:
                exit_price, exit_reason, exit_pos = opened, "stop_gap", pos
                break
            if opened >= target:
                exit_price, exit_reason, exit_pos = target, "target_gap", pos
                break
            if low <= stop:
                exit_price, exit_reason, exit_pos = stop, "stop", pos
                break
            if high >= target:
                exit_price, exit_reason, exit_pos = target, "target", pos
                break
        else:
            if opened >= stop:
                exit_price, exit_reason, exit_pos = opened, "stop_gap", pos
                break
            if opened <= target:
                exit_price, exit_reason, exit_pos = target, "target_gap", pos
                break
            if high >= stop:
                exit_price, exit_reason, exit_pos = stop, "stop", pos
                break
            if low <= target:
                exit_price, exit_reason, exit_pos = target, "target", pos
                break
    gross = side * (exit_price - fill)
    net_r = (gross - ROUND_TURN_COST_PIPS * PIP) / risk
    return {
        "status": "SIMULATED", "pair": signal["pair"], "variant": signal.get("variant"),
        "signal_close_utc": signal["signal_close_utc"], "entry_time_utc": frame.index[entry_pos].isoformat(),
        "exit_time_utc": frame.index[exit_pos].isoformat(), "side": signal["side"],
        "fill": fill, "stop": stop, "target": target, "fill_RR": fill_rr,
        "buffer_pips": buffer_pips, "allow_overnight": allow_overnight,
        "exit_price": exit_price, "exit_reason": exit_reason, "risk_distance": risk,
        "gross_R": gross / risk, "net_R": net_r,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cache_bytes = CACHE.read_bytes()
    cache = json.loads(cache_bytes)
    candidates = [signal for rows in cache["candidates_by_pair"].values() for signal in rows]
    frames = {pair: load_frame(pair) for pair in PAIRS}
    rows: list[dict] = []
    for buffer_pips in BUFFER_PIPS:
        for allow_overnight in (False, True):
            for signal in candidates:
                result = simulate(signal, frames[signal["pair"]], buffer_pips, allow_overnight)
                if result:
                    rows.append(result)
    with (OUT / "trades.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = list(rows[0]) if rows else []
        writer = csv.DictWriter(handle, fieldnames=fields)
        if fields:
            writer.writeheader(); writer.writerows(rows)
    summary = []
    for buffer_pips in BUFFER_PIPS:
        for allow_overnight in (False, True):
            subset = [r for r in rows if r.get("buffer_pips") == buffer_pips and r.get("allow_overnight") == allow_overnight and r.get("status") == "SIMULATED"]
            reasons = Counter(r["exit_reason"] for r in subset)
            net = [float(r["net_R"]) for r in subset]
            summary.append({
                "buffer_pips": buffer_pips, "allow_overnight": allow_overnight,
                "candidates": len(candidates), "simulated": len(subset),
                "invalid_or_unfilled": sum(1 for r in rows if r.get("buffer_pips") == buffer_pips and r.get("allow_overnight") == allow_overnight and r.get("status") != "SIMULATED"),
                "exit_reason_counts": dict(sorted(reasons.items())),
                "wins": sum(x > 0 for x in net), "losses": sum(x < 0 for x in net),
                "win_rate_pct": (sum(x > 0 for x in net) / len(net) * 100) if net else None,
                "total_R_net": sum(net), "average_R_net": (sum(net) / len(net)) if net else None,
            })
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    metadata = {
        "experiment": "side_stop_exit_14d",
        "production_code_changed": False,
        "signal_source": str(CACHE.relative_to(ROOT)),
        "signal_source_sha256": sha256(CACHE),
        "data_sha256": {pair: sha256(DATA / f"{pair}_m5_14d.json") for pair in PAIRS},
        "git_commit": commit,
        "period": "2026-09-13T21:40:00+00:00 to 2026-09-25T20:55:00+00:00",
        "cost_pips_round_turn": ROUND_TURN_COST_PIPS,
        "overnight_false_rule": "close at first bar whose UTC date differs from entry date",
        "intrabar_policy": "sl_first; gap checked before wick; same-bar stop wins over target",
        "buffers_pips": BUFFER_PIPS,
        "candidates": len(candidates),
        "results": summary,
    }
    (OUT / "summary.json").write_text(json.dumps(metadata, indent=2) + "\n")
    lines = ["# Side-only 14d stop/exit experiment", "", "This is a research artifact only; production code and `main` were not changed.", "", f"- Git commit: `{commit}`", f"- Frozen candidates: `{len(candidates)}` from `{CACHE.relative_to(ROOT)}`", "- Entry: next available M5 open after signal close.", "- Cost: 1.5 pip round turn.", "- `allow_overnight=false`: close at the first M5 bar on the next UTC date.", "- Intrabar policy: stop-first, with gap checks before wick checks.", "", "| Buffer (pip) | Overnight | Candidates | Simulated | Wins | Losses | Win rate | Total net R | Avg net R | Exit reasons |", "|---:|:---:|---:|---:|---:|---:|---:|---:|---:|:---|"]
    for item in summary:
        lines.append(f"| {item['buffer_pips']:.1f} | {item['allow_overnight']} | {item['candidates']} | {item['simulated']} | {item['wins']} | {item['losses']} | {item['win_rate_pct'] if item['win_rate_pct'] is not None else 'n/a'} | {item['total_R_net']:.4f} | {item['average_R_net'] if item['average_R_net'] is not None else 'n/a'} | {json.dumps(item['exit_reason_counts'], sort_keys=True)} |")
    (OUT / "report.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
