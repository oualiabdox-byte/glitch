#!/usr/bin/env python3
"""Causal CRT + Turtle Body Soup research backtest.

This is a signal-only research implementation of the rules described in the
three reference videos. It uses public Yahoo Finance 5-minute OHLC data,
2-hour CRT ranges, a higher-timeframe purge, and a lower-timeframe body-close
TBS followed by a close back through the swept level.

Default instruments are EURUSD, GBPUSD, USDJPY, and GC=F (gold futures as a
public XAU/USD proxy). Results are hypothetical and exclude spread, commission,
slippage, rollover, and contract-specific sizing.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SYMBOLS = {"EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X", "GOLD": "GC=F"}
INTERVAL = "5m"
HTF = "2h"
LOOKBACK_DAYS = 14
YAHOO_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"


@dataclass
class Trade:
    instrument: str
    symbol: str
    side: str
    signal_time: str
    entry_time: str
    entry: float
    stop: float
    equilibrium: float
    target: float
    exit_time: str
    exit_price: float
    exit_reason: str
    r_multiple: float
    htf_purge_time: str
    liquidity_level: float
    candles_between: int


def fetch_5m(symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    params = {"period1": int(start.timestamp()), "period2": int(end.timestamp()), "interval": INTERVAL, "events": "history"}
    response = requests.get(YAHOO_URL.format(symbol=symbol), params=params,
                            headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    response.raise_for_status()
    payload = response.json()
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        error = payload.get("chart", {}).get("error") or {}
        raise RuntimeError(f"No data for {symbol}: {error.get('description', 'unknown error')}")
    quote = result["indicators"]["quote"][0]
    frame = pd.DataFrame(quote, index=pd.to_datetime(result["timestamp"], unit="s", utc=True))
    frame = frame.rename(columns={"open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume"})
    frame = frame[["open", "high", "low", "close", "volume"]].sort_index()
    frame = frame[~frame.index.duplicated(keep="last")].dropna(subset=["open", "high", "low", "close"])
    valid = (frame[["open", "high", "low", "close"]] > 0).all(axis=1)
    valid &= frame.high >= frame[["open", "close", "low"]].max(axis=1)
    valid &= frame.low <= frame[["open", "close", "high"]].min(axis=1)
    frame = frame.loc[valid]
    return frame


def complete_bars(m5: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Yahoo's timestamps are bar opens. Drop incomplete HTF buckets and retain
    # only regular 5-minute bars; gaps are reported, not silently filled.
    m5 = m5[(m5.index.minute % 5 == 0)].copy()
    htf = m5.resample(HTF, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()
    counts = m5["close"].resample(HTF, label="left", closed="left").count()
    htf = htf.loc[counts[counts >= 20].index]
    return m5, htf


def atr(frame: pd.DataFrame, end: int, window: int = 14) -> float:
    sample = frame.iloc[max(0, end - window):end]
    if len(sample) < 5:
        return float(frame.close.iloc[max(0, end - 1)] * 0.0001)
    ranges = sample.high - sample.low
    value = float(ranges.mean())
    return value if value > 0 else float(frame.close.iloc[max(0, end - 1)] * 0.0001)


def htf_purges(m5: pd.DataFrame, htf: pd.DataFrame) -> dict[pd.Timestamp, dict]:
    """Return completed CRT purges keyed by the first HTF bucket after purge."""
    result: dict[pd.Timestamp, dict] = {}
    for i in range(1, len(htf)):
        if i + 1 >= len(htf):
            continue
        previous = htf.iloc[i - 1]
        purge = htf.iloc[i]
        purge_time = htf.index[i]
        # A sweep must extend beyond one CRT boundary and close back inside.
        if purge.high > previous.high and purge.close < previous.high:
            result[htf.index[i + 1]] = {
                "side": "SHORT", "crt_time": htf.index[i - 1], "purge_time": purge_time,
                "range_high": float(previous.high), "range_low": float(previous.low),
            }
        elif purge.low < previous.low and purge.close > previous.low:
            result[htf.index[i + 1]] = {
                "side": "LONG", "crt_time": htf.index[i - 1], "purge_time": purge_time,
                "range_high": float(previous.high), "range_low": float(previous.low),
            }
    return result


def body_tbs_candidates(frame: pd.DataFrame, start: int, end: int, side: str) -> list[dict]:
    """Find equal-level structures 2–6 candles apart and body-close TBS re-entry."""
    candidates = []
    for point in range(max(start + 6, 6), min(end, len(frame) - 1)):
        volatility = atr(frame, point)
        tolerance = max(volatility * 0.20, float(frame.close.iloc[point]) * 0.00003)
        for gap in range(2, 7):
            first = point - gap
            second = point
            if side == "SHORT":
                level = max(float(frame.high.iloc[first]), float(frame.high.iloc[second]))
                if abs(float(frame.high.iloc[first]) - float(frame.high.iloc[second])) > tolerance:
                    continue
                sweep = point + 1
                reentry = point + 2
                if reentry >= end:
                    continue
                if float(frame.close.iloc[sweep]) > level and float(frame.close.iloc[reentry]) < level:
                    candidates.append({"sweep": sweep, "entry": reentry, "level": level,
                                       "gap": gap, "sweep_extreme": float(frame.high.iloc[sweep])})
            else:
                level = min(float(frame.low.iloc[first]), float(frame.low.iloc[second]))
                if abs(float(frame.low.iloc[first]) - float(frame.low.iloc[second])) > tolerance:
                    continue
                sweep = point + 1
                reentry = point + 2
                if reentry >= end:
                    continue
                if float(frame.close.iloc[sweep]) < level and float(frame.close.iloc[reentry]) > level:
                    candidates.append({"sweep": sweep, "entry": reentry, "level": level,
                                       "gap": gap, "sweep_extreme": float(frame.low.iloc[sweep])})
    candidates.sort(key=lambda x: (x["entry"], x["gap"]))
    # One earliest confirmation per five-minute bar.
    seen = set()
    return [c for c in candidates if not (c["entry"] in seen or seen.add(c["entry"]))]


def simulate_trade(frame: pd.DataFrame, candidate: dict, side: str, crt: dict, htf_purge_time: pd.Timestamp) -> Trade | None:
    entry_i = candidate["entry"]
    entry = float(frame.close.iloc[entry_i])
    buffer = max(atr(frame, entry_i) * 0.05, entry * 0.00002)
    if side == "SHORT":
        stop = candidate["sweep_extreme"] + buffer
        equilibrium = (crt["range_high"] + crt["range_low"]) / 2
        target = crt["range_low"]
        risk = stop - entry
    else:
        stop = candidate["sweep_extreme"] - buffer
        equilibrium = (crt["range_high"] + crt["range_low"]) / 2
        target = crt["range_high"]
        risk = entry - stop
    if risk <= 0 or (side == "SHORT" and target >= entry) or (side == "LONG" and target <= entry):
        return None
    half_target_r = ((entry - equilibrium) / risk if side == "SHORT" else (equilibrium - entry) / risk)
    full_target_r = ((entry - target) / risk if side == "SHORT" else (target - entry) / risk)
    if half_target_r <= 0 or full_target_r <= 0:
        return None
    be_active = False
    realized = 0.0
    exit_i = None
    exit_price = None
    reason = "DATA_END"
    for i in range(entry_i + 1, len(frame)):
        high, low = float(frame.high.iloc[i]), float(frame.low.iloc[i])
        if side == "SHORT":
            # Conservative same-bar ordering: stop before target.
            if high >= (entry if be_active else stop):
                if not be_active:
                    realized = -1.0
                exit_i, exit_price, reason = i, entry if be_active else stop, "BREAKEVEN" if be_active else "STOP"
                break
            if not be_active and low <= equilibrium:
                realized += 0.5 * half_target_r
                be_active = True
            if be_active and low <= target:
                realized += 0.5 * full_target_r
                exit_i, exit_price, reason = i, target, "TARGET"
                break
        else:
            if low <= (entry if be_active else stop):
                if not be_active:
                    realized = -1.0
                exit_i, exit_price, reason = i, entry if be_active else stop, "BREAKEVEN" if be_active else "STOP"
                break
            if not be_active and high >= equilibrium:
                realized += 0.5 * half_target_r
                be_active = True
            if be_active and high >= target:
                realized += 0.5 * full_target_r
                exit_i, exit_price, reason = i, target, "TARGET"
                break
    if exit_i is None:
        exit_i = len(frame) - 1
        exit_price = float(frame.close.iloc[exit_i])
        move_r = (entry - exit_price) / risk if side == "SHORT" else (exit_price - entry) / risk
        realized += 0.5 * (move_r if be_active else move_r * 2)
    return Trade(
        instrument="", symbol="", side=side,
        signal_time=frame.index[entry_i].isoformat(), entry_time=frame.index[entry_i].isoformat(),
        entry=entry, stop=stop, equilibrium=equilibrium, target=target,
        exit_time=frame.index[exit_i].isoformat(), exit_price=float(exit_price), exit_reason=reason,
        r_multiple=realized, htf_purge_time=htf_purge_time.isoformat(),
        liquidity_level=float(candidate["level"]), candles_between=int(candidate["gap"]),
    )


def backtest(instrument: str, symbol: str, frame: pd.DataFrame) -> tuple[list[Trade], dict]:
    m5, htf = complete_bars(frame)
    purges = htf_purges(m5, htf)
    trades: list[Trade] = []
    occupied_until = -1
    htf_times = list(htf.index)
    for bucket, purge in purges.items():
        if bucket not in htf.index:
            continue
        start = int(m5.index.searchsorted(bucket))
        next_bucket = htf.index[htf.index.get_loc(bucket) + 1] if htf.index.get_loc(bucket) + 1 < len(htf) else m5.index[-1]
        end = int(m5.index.searchsorted(next_bucket))
        if end <= start + 8:
            continue
        candidates = body_tbs_candidates(m5, start, end, purge["side"])
        for candidate in candidates:
            if candidate["entry"] <= occupied_until:
                continue
            trade = simulate_trade(m5, candidate, purge["side"], purge, purge["purge_time"])
            if trade:
                trade.instrument, trade.symbol = instrument, symbol
                trades.append(trade)
                occupied_until = max(occupied_until, int(m5.index.searchsorted(pd.Timestamp(trade.exit_time))))
                break
    quality = {
        "instrument": instrument, "symbol": symbol, "source": "Yahoo Finance chart API",
        "m5_bars": int(len(m5)), "h2_bars": int(len(htf)), "htf_purges": int(len(purges)),
        "first_bar_utc": m5.index.min().isoformat() if len(m5) else None,
        "last_bar_utc": m5.index.max().isoformat() if len(m5) else None,
        "missing_5m_gaps": int(((m5.index.to_series().diff() > pd.Timedelta(minutes=10))).sum()),
    }
    return trades, quality


def summarize(trades: list[Trade], quality: list[dict], start: pd.Timestamp, end: pd.Timestamp) -> dict:
    by_instrument = {}
    for instrument in DEFAULT_SYMBOLS:
        rows = [t for t in trades if t.instrument == instrument]
        wins = [t for t in rows if t.r_multiple > 0]
        losses = [t for t in rows if t.r_multiple < 0]
        gross_win = sum(t.r_multiple for t in wins)
        gross_loss = abs(sum(t.r_multiple for t in losses))
        equity = 0.0; peak = 0.0; max_dd = 0.0
        for t in sorted(rows, key=lambda x: x.exit_time):
            equity += t.r_multiple; peak = max(peak, equity); max_dd = max(max_dd, peak - equity)
        by_instrument[instrument] = {
            "trades": len(rows), "wins": len(wins), "losses": len(losses),
            "win_rate_pct": round(100 * len(wins) / len(rows), 2) if rows else 0.0,
            "total_r": round(sum(t.r_multiple for t in rows), 4),
            "profit_factor": round(gross_win / gross_loss, 4) if gross_loss else (None if not gross_win else "inf"),
            "max_drawdown_r": round(max_dd, 4),
        }
    return {"strategy": "CRT_TBS_BODY_CLOSE_REENTRY", "period_start_utc": start.isoformat(),
            "period_end_utc": end.isoformat(), "instruments": list(DEFAULT_SYMBOLS),
            "data_quality": quality, "by_instrument": by_instrument,
            "total_trades": len(trades), "total_r": round(sum(t.r_multiple for t in trades), 4),
            "limitations": ["14 calendar days is a small sample", "Yahoo OHLC is indicative and not bid/ask executable",
                            "GC=F is a gold-futures proxy, not broker-specific XAUUSD", "no spread, slippage, commission, or financing modeled",
                            "intrabar stop/target ordering is conservative but still unknowable from OHLC"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=LOOKBACK_DAYS)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "backtest" / "crt_tbs_14d_results")
    args = parser.parse_args()
    if args.days <= 0:
        raise SystemExit("--days must be positive")
    end = pd.Timestamp.now(tz="UTC").floor("5min")
    start = end - pd.Timedelta(days=args.days)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    all_trades: list[Trade] = []
    quality: list[dict] = []
    for instrument, symbol in DEFAULT_SYMBOLS.items():
        print(f"Downloading {instrument} ({symbol}) {start.isoformat()} -> {end.isoformat()}", flush=True)
        frame = fetch_5m(symbol, start, end)
        trades, report = backtest(instrument, symbol, frame)
        all_trades.extend(trades); quality.append(report)
        print(f"  bars={report['m5_bars']} h2={report['h2_bars']} purges={report['htf_purges']} trades={len(trades)}", flush=True)
        time.sleep(0.25)
    summary = summarize(all_trades, quality, start, end)
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    pd.DataFrame([asdict(t) for t in all_trades]).to_csv(args.output_dir / "trades.csv", index=False)
    lines = ["# CRT/TBS 14-day research backtest", "", f"Period: `{start.isoformat()}` to `{end.isoformat()}`", "", "## Rules", "", "- 2-hour CRT candle; next completed candle must sweep one boundary and close back inside.", "- On the following 2-hour bucket, detect a lower-timeframe TBS: equal highs/lows 2–6 M5 candles apart, body close beyond the level, then close back through it.", "- Stop beyond sweep extreme; take 50% at CRT equilibrium, move remainder to breakeven, target opposite CRT boundary.", "", "## Results", "", "| Instrument | Trades | Win rate | Total R | Profit factor | Max DD (R) |", "|---|---:|---:|---:|---:|---:|"]
    for instrument, row in summary["by_instrument"].items():
        lines.append(f"| {instrument} | {row['trades']} | {row['win_rate_pct']:.2f}% | {row['total_r']:.4f} | {row['profit_factor']} | {row['max_drawdown_r']:.4f} |")
    lines += ["", f"**Total:** {summary['total_trades']} trades, `{summary['total_r']:.4f}R`.", "", "## Caveats", "", *[f"- {x}" for x in summary["limitations"]], ""]
    (args.output_dir / "report.md").write_text("\n".join(lines))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
