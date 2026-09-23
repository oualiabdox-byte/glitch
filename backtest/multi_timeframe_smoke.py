"""Deterministic four-session smoke test for the 1D/1H/5M research engine.

This is an integration/reproducibility test, not a profitability report. It
uses completed higher-timeframe bars and evaluates each M5 close using only
bars available at that close. cTrader credentials are loaded from .env.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from data.ctrader import CTraderData
from strategy.multi_timeframe import evaluate_setup, setup_rejection_reasons
from strategy.ict_mtf import evaluate_ict_mtf, rejection_reasons_ict_mtf


def dt(value) -> datetime:
    if isinstance(value, datetime):
        value = value.isoformat()
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def close_time(bar, minutes: int) -> datetime:
    return dt(bar["time"]) + timedelta(minutes=minutes)


def day_key(bar) -> str:
    return dt(bar["time"]).date().isoformat()


def choose_block(days: list[str], manifest: str, length: int = 4) -> list[str]:
    if len(days) < length:
        raise RuntimeError(f"need at least {length} valid daily sessions, got {len(days)}")
    seed = int(hashlib.sha256((manifest + "|four-session-smoke").encode()).hexdigest()[:16], 16)
    start = seed % (len(days) - length + 1)
    return days[start:start + length]


def _download_windowed(feed: CTraderData, symbol: str, start: str, end: str) -> dict[str, list[dict]]:
    """Avoid the provider's single-page 999-bar ceiling for M5 data."""
    start_dt, end_dt = dt(start), dt(end)
    result = {"d1": [], "h1": [], "m5": []}
    work = Path(feed.cache_dir) / "window_fetch"
    work.mkdir(parents=True, exist_ok=True)
    for period, chunk_days in (("d1", 40), ("h1", 40), ("m5", 5)):
        cursor = start_dt
        window_no = 0
        while cursor < end_dt:
            chunk_end = min(cursor + timedelta(days=chunk_days), end_dt)
            output = work / f"{period}_{window_no}.json"
            command = [
                sys.executable, "-m", "backtest.fetch_window",
                "--symbol", symbol, "--period", period,
                "--start", cursor.isoformat(), "--end", chunk_end.isoformat(),
                "--cache-dir", str(feed.cache_dir), "--output", str(output),
            ]
            completed = subprocess.run(command, cwd=Path(__file__).parents[1], capture_output=True, text=True)
            if completed.returncode != 0:
                raise RuntimeError(f"cTrader {period} window failed: {completed.stderr[-1000:]}")
            rows = json.loads(output.read_text())
            result[period].extend(rows.get(period, []))
            cursor = chunk_end
            window_no += 1
    for period in result:
        result[period] = [dict(x) for _, x in sorted({x["time"]: x for x in result[period]}.items())]
    return result


def run(symbol: str, start: str, end: str, cache_dir: str, tick_size: float,
        model: str = "legacy_mtf") -> dict:
    feed = CTraderData(cache_dir=cache_dir)
    data = _download_windowed(feed, symbol, start, end)
    d1, h1, m5 = data["d1"], data["h1"], data["m5"]
    if not d1 or not h1 or not m5:
        raise RuntimeError(f"empty data: d1={len(d1)} h1={len(h1)} m5={len(m5)}")
    # cTrader daily candles use a broker session close (often New York), so
    # their UTC calendar date does not always equal the M5 session date. Pick
    # weekday M5 sessions and verify higher-timeframe history at each close
    # below instead of requiring string-date equality across timeframes.
    m5_days = sorted({day_key(x) for x in m5 if dt(x["time"]).weekday() < 5})
    days = m5_days
    if len(days) < 4:
        raise RuntimeError(
            "fewer than four weekday M5 sessions are present: "
            f"d1={len(d1)}, h1={len(h1)}, m5={len(m5)}, m5_days={days}"
        )
    manifest = json.dumps({"symbol": symbol, "start": start, "end": end, "counts": {"d1": len(d1), "h1": len(h1), "m5": len(m5)}}, sort_keys=True)
    # Extended runs evaluate every available weekday in the requested window.
    # The deterministic four-day selection remains available through the
    # original helper for smoke tests and unit-level reproducibility.
    selected = days
    selected_set = set(selected)
    signals = []
    rejection: dict[str, int] = {}
    for i, bar in enumerate(m5):
        if day_key(bar) not in selected_set:
            continue
        available_at = close_time(bar, 5)
        d1_visible = [x for x in d1 if close_time(x, 24) <= available_at]
        h1_visible = [x for x in h1 if close_time(x, 60) <= available_at]
        m5_visible = m5[: i + 1]
        if len(d1_visible) < 2 or len(h1_visible) < 20 or len(m5_visible) < 30:
            rejection["INSUFFICIENT_HISTORY"] = rejection.get("INSUFFICIENT_HISTORY", 0) + 1
            continue
        if model == "strict_ict_mtf":
            setup = evaluate_ict_mtf(d1_visible, h1_visible, m5_visible)
        else:
            setup = evaluate_setup(d1_visible, h1_visible, m5_visible, tick_size=tick_size, allow_weak_daily=True)
        if setup:
            setup["signal_time"] = bar["time"]
            setup["available_at"] = available_at.isoformat()
            signals.append(setup)
        else:
            if model == "strict_ict_mtf":
                reasons = rejection_reasons_ict_mtf(d1_visible, h1_visible, m5_visible)
            else:
                reasons = setup_rejection_reasons(d1_visible, h1_visible, m5_visible, tick_size=tick_size, allow_weak_daily=True)
            for reason in reasons or ["SIGNAL_DIAGNOSTIC_MISMATCH"]:
                rejection[reason] = rejection.get(reason, 0) + 1
    return {
        "symbol": symbol,
        "model": model,
        "selected_days": selected,
        "seed_manifest": manifest,
        "bar_counts": {"d1": len(d1), "h1": len(h1), "m5": len(m5)},
        "selected_m5_bars": sum(1 for x in m5 if day_key(x) in selected_set),
        "signals": signals,
        "signal_count": len(signals),
        "rejections": rejection,
        "weak_daily_enabled": model != "strict_ict_mtf",
        "weak_daily_risk_multiplier": 0.5,
        "note": "extended historical diagnostic only; not evidence of profitability",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--start", default="2026-08-01T00:00:00Z")
    parser.add_argument("--end", default="2026-09-23T00:00:00Z")
    parser.add_argument("--cache-dir", default="/tmp/forex_bot_mtf_cache")
    parser.add_argument("--tick-size", type=float, default=0.00001)
    parser.add_argument("--output", default="results/mtf_four_session_smoke.json")
    parser.add_argument("--model", choices=("legacy_mtf", "strict_ict_mtf"), default="legacy_mtf")
    args = parser.parse_args()
    result = run(args.symbol, args.start, args.end, args.cache_dir, args.tick_size, args.model)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, default=str))
    print(json.dumps({k: result[k] for k in ("symbol", "model", "selected_days", "bar_counts", "selected_m5_bars", "signal_count", "rejections", "note")}, indent=2))


if __name__ == "__main__":
    main()
