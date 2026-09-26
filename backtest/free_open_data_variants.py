#!/usr/bin/env python3
"""Research backtest for all live forex presets using HistData free M1 archives.

Requires pandas and requests. Download form tokens are fetched from HistData at
runtime; no credentials or paid FTP access are used. Output fills/trades are
hypothetical. The source data are bid-only one-minute bars, not executable quotes.
"""
from __future__ import annotations

import argparse
import csv
from concurrent.futures import ProcessPoolExecutor, as_completed
import io
import json
import re
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASE_URL = "https://www.histdata.com"
SYMBOLS = ("EURUSD", "GBPUSD")
from strategy.variants import VARIANTS as VARIANT_CONFIGS
from strategy.selection import select_signals, signal_identity

VARIANTS = tuple((spec["pair"], name) for name, spec in VARIANT_CONFIGS.items())
PIP = 0.0001
RISK_PER_TRADE = 0.005
DEFAULT_COST_PIPS = 1.5
DEFAULT_LOOKBACK_DAYS = 30
TRADE_COLUMNS = [
    "pair", "variant", "signal_id", "signal_close_utc", "event_time_utc", "side",
    "entry_reference", "stop", "target", "planned_rr", "fill_time_utc",
    "fill_reference_bid_open", "exit_time_utc", "exit_price_reference",
    "exit_reason", "risk_distance", "gross_pnl_price", "gross_r",
    "cost_pips_round_turn", "cost_price", "net_r", "risk_budget_pct",
    "trade_return_pct", "equity_before", "equity_after",
]
# HistData states its timestamps use fixed EST (UTC-05:00), without DST.
SOURCE_TZ = timezone(timedelta(hours=-5))


class DownloadForm(HTMLParser):
    """Collect one named form and its hidden input values using stdlib HTMLParser."""
    def __init__(self, form_id: str):
        super().__init__()
        self.form_id = form_id
        self.inside = False
        self.action = None
        self.values: dict[str, str] = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form" and attrs.get("id") == self.form_id:
            self.inside = True
            self.action = attrs.get("action")
        elif self.inside and tag == "input" and attrs.get("name"):
            self.values[attrs["name"]] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form" and self.inside:
            self.inside = False


def month_page(pair: str, year: int, month: int) -> str:
    return (f"{BASE_URL}/download-free-forex-historical-data/"
            f"?/ascii/1-minute-bar-quotes/{pair.lower()}/{year}/{month}")


def _form(page_html: str, name: str) -> DownloadForm:
    parser = DownloadForm(name)
    parser.feed(page_html)
    if not parser.action or not parser.values:
        raise RuntimeError(f"HistData download form {name!r} was not found")
    return parser


def download_month(pair: str, year: int, month: int, data_dir: Path, refresh: bool = False) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    output = data_dir / f"{pair}_{year}{month:02d}.zip"
    page_url = month_page(pair, year, month)
    status_output = data_dir / f"{pair}_{year}{month:02d}_status.txt"
    if output.is_file() and status_output.is_file() and not refresh:
        return output
    session = requests.Session()
    page = session.get(page_url, timeout=30)
    page.raise_for_status()
    form = _form(page.text, "file_down")
    response = session.post(
        urljoin(BASE_URL, form.action), data=form.values,
        headers={"Referer": page_url, "User-Agent": "Mozilla/5.0"}, timeout=90,
    )
    response.raise_for_status()
    if not response.content.startswith(b"PK"):
        raise RuntimeError(f"HistData did not return a ZIP for {pair} {year}-{month:02d}")
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        if not archive.namelist() or archive.testzip() is not None:
            raise RuntimeError(f"HistData ZIP failed integrity validation: {pair} {year}-{month:02d}")
    output.write_bytes(response.content)
    status_form = _form(page.text, "file_status")
    status_response = session.post(
        urljoin(BASE_URL, status_form.action), data=status_form.values,
        headers={"Referer": page_url, "User-Agent": "Mozilla/5.0"}, timeout=60,
    )
    status_response.raise_for_status()
    if not status_response.content:
        raise RuntimeError(f"HistData returned an empty status report for {pair} {year}-{month:02d}")
    status_output.write_bytes(status_response.content)
    return output


def _months_between(start: pd.Timestamp, end: pd.Timestamp) -> list[tuple[int, int]]:
    current = start.to_pydatetime().replace(day=1)
    last = end.to_pydatetime().replace(day=1)
    result = []
    while current <= last:
        result.append((current.year, current.month))
        current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
    return result


def _load_pair(pair: str, data_dir: Path, start: pd.Timestamp, end: pd.Timestamp,
               refresh: bool = False) -> tuple[pd.DataFrame, dict]:
    paths = [download_month(pair, year, month, data_dir, refresh)
             for year, month in _months_between(start, end)]
    parts = []
    archive_files = []
    for path in paths:
        with zipfile.ZipFile(path) as archive:
            csv_name = next((name for name in archive.namelist() if name.lower().endswith(".csv")), None)
            if csv_name is None:
                raise RuntimeError(f"No CSV in archive {path.name}")
            archive_files.append({"name": path.name, "bytes": path.stat().st_size,
                                  "member": csv_name,
                                  "provider_status_file": f"{path.stem}_status.txt"})
            with archive.open(csv_name) as handle:
                frame = pd.read_csv(
                    handle, sep=";", header=None,
                    names=["timestamp", "open", "high", "low", "close", "volume"],
                    usecols=[0, 1, 2, 3, 4, 5],
                )
                parts.append(frame)
    data = pd.concat(parts, ignore_index=True)
    input_rows = len(data)
    stamps = pd.to_datetime(data.pop("timestamp"), format="%Y%m%d %H%M%S", errors="coerce")
    invalid_timestamp = int(stamps.isna().sum())
    data.index = stamps.dt.tz_localize(SOURCE_TZ).dt.tz_convert("UTC")
    data = data.loc[~data.index.isna()].sort_index()
    duplicates = int(data.index.duplicated(keep="last").sum())
    data = data.loc[~data.index.duplicated(keep="last")]
    for column in ("open", "high", "low", "close", "volume"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    valid = (
        data[["open", "high", "low", "close"]].notna().all(axis=1)
        & (data[["open", "high", "low", "close"]] > 0).all(axis=1)
        & (data["high"] >= data[["open", "close", "low"]].max(axis=1))
        & (data["low"] <= data[["open", "close", "high"]].min(axis=1))
    )
    invalid_ohlc = int((~valid).sum())
    data = data.loc[valid, ["open", "high", "low", "close"]]
    data = data.loc[(data.index >= start) & (data.index < end)]

    def aggregate(rule: str, expected_count: int):
        grouped = data.resample(rule, label="left", closed="left")
        bars = grouped.agg({"open": "first", "high": "max", "low": "min", "close": "last"})
        counts = grouped["close"].count()
        incomplete = int(((counts > 0) & (counts < expected_count)).sum())
        complete = bars.loc[counts == expected_count].dropna()
        return complete, incomplete, int((counts > expected_count).sum())

    m5, incomplete_m5, extra_m5 = aggregate("5min", 5)
    h1, incomplete_h1, extra_h1 = aggregate("1h", 60)
    if len(m5) < 20 or len(h1) < 20:
        raise RuntimeError(f"Insufficient complete bars for {pair}: M5={len(m5)} H1={len(h1)}")
    quality = {
        "pair": pair, "archive_files": archive_files,
        "rows_in_archives": input_rows, "rows_after_filter": len(data),
        "invalid_timestamps": invalid_timestamp, "duplicate_timestamps_removed": duplicates,
        "invalid_ohlc_rows_removed": invalid_ohlc,
        "m5_complete_bars": len(m5), "incomplete_m5_buckets_dropped": incomplete_m5,
        "h1_complete_bars": len(h1), "incomplete_h1_buckets_dropped": incomplete_h1,
        "last_m1_open_utc": data.index.max().isoformat(),
        "last_complete_m5_open_utc": m5.index.max().isoformat(),
        "last_complete_h1_open_utc": h1.index.max().isoformat(),
        "m5_resample_rows_with_more_than_expected_minutes": extra_m5,
        "h1_resample_rows_with_more_than_expected_minutes": extra_h1,
    }
    return data, {"m5": m5, "h1": h1, "quality": quality}


def _rows(frame: pd.DataFrame) -> list[dict]:
    return [{"time": ts.isoformat(), "open": float(row.open), "high": float(row.high),
             "low": float(row.low), "close": float(row.close)}
            for ts, row in frame.iterrows()]


def collect_signals(pair: str, variant: str, h1: pd.DataFrame, m5: pd.DataFrame,
                    trade_start: pd.Timestamp, trade_end: pd.Timestamp,
                    lookback_days: int) -> list[dict]:
    sys.path.insert(0, str(ROOT))
    from config.settings import load_config, strategy_config
    from strategy.variants import build_variant

    strategy = build_variant(variant, base_options=strategy_config(load_config()))
    h1_rows = _rows(h1)
    h1_closes = h1.index + pd.Timedelta(1, unit="h")
    m5_rows = _rows(m5)
    m5_times = m5.index
    seen_events: set[str] = set()
    setup_state = None
    output = []
    # Evaluate one pre-window bar to seed the persistent setup state, then scan
    # only the requested window while still passing each evaluation its full
    # rolling lookback. This avoids reprocessing 30 warm-up days bar by bar.
    first_test_index = max(0, int(m5_times.searchsorted(
        trade_start - pd.Timedelta(10, unit="min"), side="left")))
    for i in range(first_test_index, len(m5_times)):
        timestamp = m5_times[i]
        signal_close = timestamp + pd.Timedelta(5, unit="min")
        if signal_close >= trade_end:
            break
        if (i - first_test_index) % 250 == 0:
            print(f"  {variant}: scanning {signal_close.isoformat()}", flush=True)
        lookback_start = signal_close - pd.Timedelta(lookback_days, unit="D")
        m5_left = int(m5_times.searchsorted(lookback_start, side="left"))
        h1_left = int(h1_closes.searchsorted(lookback_start, side="left"))
        h1_right = int(h1_closes.searchsorted(signal_close, side="right"))
        recent_h1 = h1_rows[h1_left:h1_right]
        decision = strategy.evaluate(recent_h1, m5_rows[m5_left:i + 1], setup_state=setup_state)
        evidence = decision.evidence
        structure = evidence.get("h1_structure", {})
        poi = evidence.get("h1_poi", {})
        lifecycle = evidence.get("poi_state", {})
        if structure.get("side") and structure.get("last_event") and poi:
            setup_state = {
                "side": structure["side"], "h1_structure": structure,
                "h1_poi": poi, "poi_formed_time": lifecycle.get("poi_formed_time"),
                "poi_touch_time": lifecycle.get("poi_touch_time"),
                "poi_active": lifecycle.get("poi_active", False),
                "confirmation_invalidated": lifecycle.get("confirmation_invalidated", False),
                "target_invalidated": lifecycle.get("target_invalidated", False),
                "invalidated_at": lifecycle.get("invalidated_at"),
                "status": lifecycle.get("status", "IDENTIFIED"),
                "updated_at": signal_close.isoformat(),
            }
        else:
            setup_state = None
        if signal_close < trade_start or signal_close >= trade_end:
            continue
        if not decision.is_signal:
            continue
        event = decision.evidence.get("m5_bos", {})
        event_time = event.get("time")
        if not event_time or event_time in seen_events:
            continue
        seen_events.add(event_time)
        signal = {
            "pair": pair, "variant": variant,
            "signal_close_utc": signal_close.isoformat(),
            "event_time_utc": pd.Timestamp(event_time).isoformat(),
            "side": "LONG" if decision.side == "LONG" else "SHORT",
            "entry_reference": float(decision.entry_price),
            "stop": float(decision.stop_price), "target": float(decision.target_price),
            "planned_rr": float(decision.risk_reward or 0.0),
        }
        signal["signal_id"] = signal_identity(signal)
        output.append(signal)
    return output


def select_pair_signals(pair: str, candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    """Resolve simultaneous preset signals with the exact live selector."""
    expected = tuple(name for configured_pair, name in VARIANTS if configured_pair == pair)
    by_close: dict[str, list[dict]] = {}
    for candidate in candidates:
        by_close.setdefault(str(candidate["signal_close_utc"]), []).append(candidate)
    selected = []
    audit = []
    for close_time in sorted(by_close):
        at_close = by_close[close_time]
        present = {str(row["variant"]) for row in at_close}
        complete_results = [{**row, "status": "SIGNAL_ONLY"} for row in at_close]
        complete_results.extend(
            {"pair": pair, "variant": name, "status": "NO_TRADE"}
            for name in expected if name not in present
        )
        decision = select_signals(complete_results, expected_variants=expected)
        winning_signal = decision.get("selected_signal")
        if winning_signal:
            selected.append(winning_signal)
        audit.append({
            "pair": pair,
            "signal_close_utc": close_time,
            "status": decision["status"],
            "selected_variant": winning_signal.get("variant") if winning_signal else None,
            "selected_signal_id": decision.get("selected_signal_id"),
            "candidate_signal_ids": json.dumps(decision.get("candidate_signal_ids", [])),
            "conflict": json.dumps(decision.get("conflict"), sort_keys=True),
            "reason": decision.get("reason"),
        })
    return selected, audit


def simulate(signals: list[dict], m1: pd.DataFrame, cost_pips: float = DEFAULT_COST_PIPS,
             window_end: pd.Timestamp | None = None) -> tuple[list[dict], dict]:
    if not signals:
        return [], {"signals": 0, "filled": 0, "skipped_while_position_open": 0,
                    "skipped_invalid_fill": 0, "skipped_no_future_bar": 0}
    signals = sorted(signals, key=lambda row: row["signal_close_utc"])
    times = m1.index
    last_index = len(m1) - 1
    if window_end is not None:
        last_index = min(last_index, int(times.searchsorted(window_end, side="left")) - 1)
    if last_index < 0:
        return [], {"signals": len(signals), "filled": 0, "skipped_while_position_open": 0,
                    "skipped_invalid_fill": 0, "skipped_no_future_bar": len(signals)}
    trades = []
    cursor_after_exit = -1
    counts = {"signals": len(signals), "filled": 0, "skipped_while_position_open": 0,
              "skipped_invalid_fill": 0, "skipped_no_future_bar": 0}
    equity = 1.0
    for signal in signals:
        signal_time = pd.Timestamp(signal["signal_close_utc"])
        if window_end is not None and signal_time >= window_end:
            continue
        entry_index = int(times.searchsorted(signal_time, side="left"))
        if entry_index > last_index:
            counts["skipped_no_future_bar"] += 1
            continue
        if entry_index <= cursor_after_exit:
            counts["skipped_while_position_open"] += 1
            continue
        side = 1 if signal["side"] == "LONG" else -1
        fill = float(m1.iloc[entry_index].open)
        stop, target = float(signal["stop"]), float(signal["target"])
        if (side == 1 and not stop < fill < target) or (side == -1 and not target < fill < stop):
            counts["skipped_invalid_fill"] += 1
            continue
        risk_distance = abs(fill - stop)
        exit_price = float(m1.iloc[last_index].close)
        reason = "end_of_sample_mark"
        exit_index = last_index
        for j in range(entry_index, last_index + 1):
            bar = m1.iloc[j]
            # Conservative stop-first policy if a single one-minute OHLC bar hits both.
            if side == 1:
                if float(bar.open) <= stop:
                    exit_price, reason, exit_index = float(bar.open), "stop_gap", j
                    break
                if float(bar.open) >= target:
                    exit_price, reason, exit_index = target, "target_gap", j
                    break
                if float(bar.low) <= stop:
                    exit_price, reason, exit_index = stop, "stop", j
                    break
                if float(bar.high) >= target:
                    exit_price, reason, exit_index = target, "target", j
                    break
            else:
                if float(bar.open) >= stop:
                    exit_price, reason, exit_index = float(bar.open), "stop_gap", j
                    break
                if float(bar.open) <= target:
                    exit_price, reason, exit_index = target, "target_gap", j
                    break
                if float(bar.high) >= stop:
                    exit_price, reason, exit_index = stop, "stop", j
                    break
                if float(bar.low) <= target:
                    exit_price, reason, exit_index = target, "target", j
                    break
        gross_pnl = side * (exit_price - fill)
        gross_r = gross_pnl / risk_distance
        cost_price = cost_pips * PIP
        net_r = (gross_pnl - cost_price) / risk_distance
        risk_pct_return = RISK_PER_TRADE * net_r
        equity_before = equity
        equity *= 1.0 + risk_pct_return
        trades.append({
            **signal,
            "fill_time_utc": times[entry_index].isoformat(), "fill_reference_bid_open": fill,
            "exit_time_utc": times[exit_index].isoformat(), "exit_price_reference": exit_price,
            "exit_reason": reason, "risk_distance": risk_distance,
            "gross_pnl_price": gross_pnl, "gross_r": gross_r,
            "cost_pips_round_turn": cost_pips, "cost_price": cost_price,
            "net_r": net_r, "risk_budget_pct": RISK_PER_TRADE * 100,
            "trade_return_pct": risk_pct_return * 100,
            "equity_before": equity_before, "equity_after": equity,
        })
        cursor_after_exit = exit_index
        counts["filled"] += 1
    return trades, counts


def summarize(trades: list[dict], cost_pips: float = DEFAULT_COST_PIPS) -> dict:
    values = [float(row["net_r"]) for row in trades]
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for value in values:
        equity *= 1 + RISK_PER_TRADE * value
        peak = max(peak, equity)
        max_dd = max(max_dd, 1 - equity / peak)
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "trades": len(trades), "wins": len(wins), "losses": len(losses),
        "breakeven": len(values) - len(wins) - len(losses),
        "win_rate_pct": (len(wins) / len(values) * 100) if values else None,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "expectancy_net_r": sum(values) / len(values) if values else None,
        "average_win_r": sum(wins) / len(wins) if wins else None,
        "average_loss_r": sum(losses) / len(losses) if losses else None,
        "total_return_pct": (equity - 1) * 100,
        "closed_trade_equity_max_drawdown_pct": max_dd * 100,
        "cost_pips_round_turn": cost_pips,
    }


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = fieldnames or (list(rows[0]) if rows else [])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2026-09-11T22:00:00Z", help="UTC test-window start")
    parser.add_argument("--end", default="2026-09-18T22:00:00Z", help="UTC end (exclusive)")
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS,
                        help="rolling strategy history in days (default matches the live scanner)")
    parser.add_argument("--data-dir", type=Path, default=Path("/tmp/forex-open-data"))
    parser.add_argument("--output-dir", type=Path, default=ROOT / "backtest" / "free_open_data_run")
    parser.add_argument("--workers", type=int, default=3,
                        help="maximum parallel variant scans (default 3)")
    parser.add_argument("--refresh", action="store_true", help="re-download monthly ZIP archives")
    args = parser.parse_args()
    start, end = pd.Timestamp(args.start), pd.Timestamp(args.end)
    if start.tzinfo is None or end.tzinfo is None or end <= start:
        raise SystemExit("start/end must be timezone-qualified and end must be after start")
    start, end = start.tz_convert("UTC"), end.tz_convert("UTC")
    if args.lookback_days < 20:
        raise SystemExit("lookback-days must be at least 20 to cover the strategy's history requirement")
    if args.workers < 1:
        raise SystemExit("workers must be at least 1")
    history_start = start - pd.Timedelta(args.lookback_days, unit="D")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    data_by_pair = {}
    quality = {}
    for pair in SYMBOLS:
        print(f"Loading official HistData M1 archives and checking complete bars: {pair}", flush=True)
        m1, frames = _load_pair(pair, args.data_dir, history_start, end, args.refresh)
        data_by_pair[pair] = (m1, frames)
        quality[pair] = frames["quality"]
        print(f"  {pair}: {len(m1):,} M1 rows, {len(frames['m5']):,} complete M5 bars, "
              f"{len(frames['h1']):,} complete H1 bars", flush=True)

    all_trades = []
    selected_pair_trades = []
    result_rows = []
    pair_selection_rows = []
    selection_audit_rows = []
    simulation_counts = {}
    sensitivity_rows = []
    split = start + (end - start) * 0.70
    candidates_by_variant = {}
    futures = {}
    with ProcessPoolExecutor(max_workers=min(args.workers, len(VARIANTS))) as pool:
        for pair, variant in VARIANTS:
            print(f"Starting {variant} on {pair}...", flush=True)
            _, frames = data_by_pair[pair]
            future = pool.submit(collect_signals, pair, variant, frames["h1"], frames["m5"],
                                 start, end, args.lookback_days)
            futures[future] = (pair, variant)
        for future in as_completed(futures):
            pair, variant = futures[future]
            candidates_by_variant[(pair, variant)] = future.result()
            print(f"Finished {variant}: {len(candidates_by_variant[(pair, variant)])} candidate signals",
                  flush=True)

    for pair, variant in VARIANTS:
        m1, frames = data_by_pair[pair]
        candidates = candidates_by_variant[(pair, variant)]
        sample = m1.loc[(m1.index >= start) & (m1.index < end)]
        if sample.empty:
            raise RuntimeError(f"No M1 data for {pair} in requested test window {start} to {end}")
        trades, counts = simulate(candidates, m1)
        simulation_counts[variant] = counts
        all_trades.extend(trades)
        base = summarize(trades)
        in_candidates = [s for s in candidates if pd.Timestamp(s["signal_close_utc"]) < split]
        out_candidates = [s for s in candidates if pd.Timestamp(s["signal_close_utc"]) >= split]
        in_trades, in_counts = simulate(in_candidates, m1, window_end=split)
        out_trades, out_counts = simulate(out_candidates, m1, window_end=end)
        in_sample = summarize(in_trades)
        out_sample = summarize(out_trades)
        last_px = float(sample.iloc[-1].close)
        first_px = float(sample.iloc[0].close)
        result_rows.append({
            "pair": pair, "variant": variant,
            "swing_length": VARIANT_CONFIGS[variant]["swing_length"],
            "m5_confirmation_mode": VARIANT_CONFIGS[variant]["m5_confirmation_mode"],
            "test_start_utc": start.isoformat(), "test_end_exclusive_utc": end.isoformat(),
            "spot_price_change_pct_no_carry": (last_px / first_px - 1) * 100,
            **base, "signals_generated": counts["signals"],
            "signals_filled": counts["filled"],
            "signals_skipped_position_open": counts["skipped_while_position_open"],
            "signals_skipped_invalid_fill": counts["skipped_invalid_fill"],
            "signals_without_future_bar": counts["skipped_no_future_bar"],
            "in_sample": {**in_sample, "signals": in_counts["signals"],
                           "fills": in_counts["filled"], "window_end_utc": split.isoformat()},
            "out_of_sample": {**out_sample, "signals": out_counts["signals"],
                              "fills": out_counts["filled"], "window_end_utc": end.isoformat()},
        })
        for stress_cost in (0.0, 1.5, 3.0, 5.0):
            stress_trades = []
            for trade in trades:
                stressed = dict(trade)
                stressed["net_r"] = stressed["gross_r"] - stress_cost * PIP / stressed["risk_distance"]
                stress_trades.append(stressed)
            sensitivity_rows.append({"pair": pair, "variant": variant,
                                     **summarize(stress_trades, cost_pips=stress_cost)})

    for pair in SYMBOLS:
        m1, _frames = data_by_pair[pair]
        pair_candidates = [candidate
                           for configured_pair, variant in VARIANTS if configured_pair == pair
                           for candidate in candidates_by_variant[(configured_pair, variant)]]
        selected_candidates, audit = select_pair_signals(pair, pair_candidates)
        selection_audit_rows.extend(audit)
        selected_trades, counts = simulate(selected_candidates, m1, window_end=end)
        selected_pair_trades.extend(selected_trades)
        pair_selection_rows.append({
            "pair": pair,
            "registered_variants": ";".join(name for configured_pair, name in VARIANTS
                                               if configured_pair == pair),
            "candidate_signals": len(pair_candidates),
            "selected_opportunities": len(selected_candidates),
            "conflicts": sum(row["status"] == "CONFLICT" for row in audit),
            "selector_status_counts": json.dumps({status: sum(
                row["status"] == status for row in audit
            ) for status in sorted({row["status"] for row in audit})}, sort_keys=True),
            "pair_level_fills": counts["filled"],
            "skipped_while_pair_position_open": counts["skipped_while_position_open"],
            **summarize(selected_trades),
        })

    output = args.output_dir
    _write_csv(output / "variant_summary.csv", result_rows)
    _write_csv(output / "trade_log.csv", all_trades, TRADE_COLUMNS)
    _write_csv(output / "pair_selected_trade_log.csv", selected_pair_trades, TRADE_COLUMNS)
    _write_csv(output / "pair_selection_summary.csv", pair_selection_rows)
    _write_csv(output / "signal_selection.csv", selection_audit_rows,
               ["pair", "signal_close_utc", "status", "selected_variant",
                "selected_signal_id", "candidate_signal_ids", "conflict", "reason"])
    _write_csv(output / "cost_sensitivity.csv", sensitivity_rows)
    metadata = {
        "data_source": "HistData.com free Generic ASCII M1 archives",
        "data_source_url": "https://www.histdata.com/download-free-forex-data/",
        "data_specification_url": "https://www.histdata.com/f-a-q/data-files-detailed-specification/",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_timezone": "Fixed EST (UTC-05:00), no daylight-saving adjustment, per provider",
        "price_basis": "Bid OHLC only; not executable bid/ask or mid-price",
        "aggregation": "Only complete five-row M5 bars and complete sixty-row H1 bars retained",
        "test_start_utc": start.isoformat(), "test_end_exclusive_utc": end.isoformat(),
        "warmup_days": args.lookback_days,
        "live_strategy_lookback_days": args.lookback_days,
        "max_parallel_variant_workers": min(args.workers, len(VARIANTS)),
        "one_position_at_a_time_per_variant_pair": True,
        "live_signal_selection": "Same strategy.selection.select_signals used by the scanner; all variant candidates at the same pair and closed-bar timestamp are evaluated before selection.",
        "pair_selected_trade_simulation": "One selected signal per pair/timestamp and one pair-level position at a time; opposing directions are recorded as conflicts and not traded.",
        "entry": "First available M1 bar open at/after the signal M5 close; this is a hypothetical next-minute reference fill",
        "intrabar_policy": "One-minute OHLC stop-first when both stop and target are touched",
        "transaction_cost": "1.5 pips round-turn base estimate; 0/3/5 pip sensitivity also reported; no separate swap or commission",
        "risk_budget_per_trade_pct": RISK_PER_TRADE * 100,
        "provider_quality": quality,
        "provider_status_files": {
            f"{pair}_{year}{month:02d}": {
                "path": str(args.data_dir / f"{pair}_{year}{month:02d}_status.txt"),
                "gap_lines": sum(
                    line.startswith("Gap of ")
                    for line in (args.data_dir / f"{pair}_{year}{month:02d}_status.txt")
                    .read_text(errors="replace").splitlines()
                ),
                "reported_max_tick_gap_ms": next((
                    int(match.group(1))
                    for line in reversed((args.data_dir / f"{pair}_{year}{month:02d}_status.txt")
                                         .read_text(errors="replace").splitlines())
                    if (match := re.search(r"Maximum tick interval found: (\d+) miliseconds", line))
                ), None),
            }
            for pair in SYMBOLS
            for year, month in _months_between(history_start, end)
        },
        "simulation_counts": simulation_counts,
        "notes": [
            "HistData provider page reports M1 Bid OHLC, missing data gaps, no volume information, and fixed EST timestamps without DST.",
            "No ask-side quotes, actual broker spread, commission, swap, market impact, financing, or rejected/partial fills are available in these M1 files.",
            "End-of-sample open positions are marked at the last available M1 close and tagged end_of_sample_mark.",
            "Closed-trade equity drawdown excludes intratrade mark-to-market drawdown.",
            "This is an exploratory short-window test; the 70/30 calendar split is descriptive, not statistically sufficient out-of-sample validation.",
        ],
    }
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(pd.DataFrame(result_rows).to_string(index=False), flush=True)
    print(f"\nSaved results to {output}")


if __name__ == "__main__":
    main()
