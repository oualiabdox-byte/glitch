"""Deterministic four-session smoke test for the 1D/1H/5M research engine.

This is an integration/reproducibility test, not a profitability report. It
uses completed higher-timeframe bars and evaluates each M5 close using only
bars available at that close. cTrader credentials are loaded from .env.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from data.ctrader import CTraderData
from strategy.multi_timeframe import evaluate_setup


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


def run(symbol: str, start: str, end: str, cache_dir: str, tick_size: float) -> dict:
    feed = CTraderData(cache_dir=cache_dir)
    data = feed.download(symbol, start, end, periods=("d1", "h1", "m5"))
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
    selected = choose_block(days, manifest)
    selected_set = set(selected)
    signals = []
    rejection = {"insufficient_htf": 0, "no_setup": 0}
    for i, bar in enumerate(m5):
        if day_key(bar) not in selected_set:
            continue
        available_at = close_time(bar, 5)
        d1_visible = [x for x in d1 if close_time(x, 24) <= available_at]
        h1_visible = [x for x in h1 if close_time(x, 60) <= available_at]
        m5_visible = m5[: i + 1]
        if len(d1_visible) < 2 or len(h1_visible) < 20 or len(m5_visible) < 30:
            rejection["insufficient_htf"] += 1
            continue
        setup = evaluate_setup(d1_visible, h1_visible, m5_visible, tick_size=tick_size)
        if setup:
            setup["signal_time"] = bar["time"]
            setup["available_at"] = available_at.isoformat()
            signals.append(setup)
        else:
            rejection["no_setup"] += 1
    return {
        "symbol": symbol,
        "selected_days": selected,
        "seed_manifest": manifest,
        "bar_counts": {"d1": len(d1), "h1": len(h1), "m5": len(m5)},
        "selected_m5_bars": sum(1 for x in m5 if day_key(x) in selected_set),
        "signals": signals,
        "signal_count": len(signals),
        "rejections": rejection,
        "note": "four-session smoke test only; not evidence of profitability",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--start", default="2026-08-01T00:00:00Z")
    parser.add_argument("--end", default="2026-09-23T00:00:00Z")
    parser.add_argument("--cache-dir", default="/tmp/forex_bot_mtf_cache")
    parser.add_argument("--tick-size", type=float, default=0.00001)
    parser.add_argument("--output", default="results/mtf_four_session_smoke.json")
    args = parser.parse_args()
    result = run(args.symbol, args.start, args.end, args.cache_dir, args.tick_size)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, default=str))
    print(json.dumps({k: result[k] for k in ("symbol", "selected_days", "bar_counts", "selected_m5_bars", "signal_count", "rejections", "note")}, indent=2))


if __name__ == "__main__":
    main()
