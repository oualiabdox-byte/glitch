#!/usr/bin/env python3
"""Research backtest for canonical strategy presets on free Yahoo 5m data.

Each preset is an independent configuration of the canonical Strategy. The
separate pair-level simulation uses the same deterministic selector as the live
scanner; Yahoo candles remain indicative, not executable bid/ask history.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path
import sys

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.settings import load_config, strategy_config
from strategy.selection import select_signals
from strategy.variants import VARIANTS, build_variant

PAIRS = {"EURUSD": ("EURUSD=X", 0.0001), "GBPUSD": ("GBPUSD=X", 0.0001)}
CASES = tuple(
    {"pair": spec["pair"], "variant": name,
     "swing": spec["swing_length"], "mode": spec["m5_confirmation_mode"]}
    for name, spec in VARIANTS.items()
)


def fetch(pair, days, cache, refresh=False):
    ticker, _ = PAIRS[pair]
    cache.mkdir(exist_ok=True)
    path = cache / f"{pair}_5m_{days}d.csv"
    if path.exists() and not refresh:
        return pd.read_csv(path, parse_dates=["timestamp"], index_col="timestamp")
    end = int(time.time())
    start = end - days * 86400
    response = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
        params={"period1": start, "period2": end, "interval": "5m",
                "includePrePost": "true", "events": "div,splits"},
        headers={"User-Agent": "Mozilla/5.0"}, timeout=30,
    )
    response.raise_for_status()
    result = response.json().get("chart", {}).get("result") or []
    if not result:
        raise RuntimeError(f"No Yahoo data for {pair}")
    item = result[0]
    quote = item["indicators"]["quote"][0]
    data = pd.DataFrame({
        "timestamp": pd.to_datetime(item["timestamp"], unit="s", utc=True),
        "open": quote["open"], "high": quote["high"],
        "low": quote["low"], "close": quote["close"],
    })
    data = data.dropna().drop_duplicates("timestamp").set_index("timestamp").sort_index()
    data.to_csv(path)
    return data


def rows(data):
    return [{"time": stamp.isoformat(), "open": float(row.open),
             "high": float(row.high), "low": float(row.low),
             "close": float(row.close)} for stamp, row in data.iterrows()]


def signals(raw, variant, base_options):
    h1 = raw.resample("1h", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}
    ).dropna()
    m5_rows = rows(raw)
    h1_rows = rows(h1)
    strategy = build_variant(variant, base_options=base_options)
    output = []
    last_event = None
    for index in range(100, len(m5_rows)):
        current_open = pd.Timestamp(m5_rows[index]["time"])
        cutoff = current_open.floor("1h")
        closed_h1 = [
            row for row in h1_rows
            if pd.Timestamp(row["time"]) + pd.Timedelta(hours=1) <= cutoff
        ]
        if len(closed_h1) < 20:
            continue
        decision = strategy.evaluate(closed_h1, m5_rows[:index + 1])
        if not decision.is_signal:
            continue
        event = decision.evidence.get("m5_bos", {})
        event_time = event.get("time")
        if not event_time or event_time == last_event:
            continue
        last_event = event_time
        signal_close = current_open + pd.Timedelta(minutes=5)
        output.append({
            "pair": VARIANTS[variant]["pair"],
            "status": "SIGNAL_ONLY", "variant": variant,
            "signal_close_utc": signal_close.isoformat(),
            "time": pd.Timestamp(event_time),
            "side": "LONG" if decision.side == "LONG" else "SHORT",
            "entry": float(decision.entry_price), "sl": float(decision.stop_price),
            "tp": float(decision.target_price), "rr": float(decision.risk_reward or 0),
            "min_rr": float(base_options.get("min_rr", 0.0)),
        })
    return output


def select_pair_candidates(pair, by_variant):
    """Use the live selector for every timestamp at which any preset signals."""
    expected = tuple(case["variant"] for case in CASES if case["pair"] == pair)
    grouped = {}
    for variant, candidates in by_variant.items():
        for candidate in candidates:
            grouped.setdefault(candidate["signal_close_utc"], {})[variant] = candidate
    selected = []
    audit = []
    for close_time in sorted(grouped):
        present = grouped[close_time]
        results = [present.get(variant) or {
            "pair": pair, "variant": variant, "status": "NO_TRADE",
        } for variant in expected]
        decision = select_signals(results, expected_variants=expected)
        signal = decision.get("selected_signal")
        if signal:
            selected.append(signal)
        audit.append({
            "pair": pair, "signal_close_utc": close_time,
            "status": decision["status"],
            "selected_variant": signal.get("variant") if signal else None,
            "candidate_signal_ids": decision.get("candidate_signal_ids", []),
            "conflict": decision.get("conflict"),
        })
    return selected, audit


def simulate(raw, signal, pip):
    # The executable fill is the next M5 open after signal close, not the
    # confirmation candle close used as the strategy's reference price.
    signal_close = pd.Timestamp(signal["signal_close_utc"])
    index = raw.index.searchsorted(signal_close, side="left")
    if index >= len(raw):
        return None
    side = 1 if signal["side"] == "LONG" else -1
    fill = float(raw.iloc[index].open)
    stop, target = float(signal["sl"]), float(signal["tp"])
    risk_distance = abs(fill - stop)
    reward_distance = side * (target - fill)
    if risk_distance <= 0 or reward_distance <= 0:
        return None
    actual_rr = reward_distance / risk_distance
    if actual_rr < float(signal.get("min_rr", 0.0)):
        return None
    reason = "end"
    exit_price = float(raw.iloc[-1].close)
    exit_index = len(raw) - 1
    for cursor in range(index, len(raw)):
        bar = raw.iloc[cursor]
        if side == 1:
            if bar.open <= stop:
                exit_price, reason, exit_index = float(bar.open), "stop_gap", cursor
                break
            if bar.open >= target:
                exit_price, reason, exit_index = target, "target_gap", cursor
                break
            if bar.low <= stop:
                exit_price, reason, exit_index = stop, "sl", cursor
                break
            if bar.high >= target:
                exit_price, reason, exit_index = target, "tp", cursor
                break
        else:
            if bar.open >= stop:
                exit_price, reason, exit_index = float(bar.open), "stop_gap", cursor
                break
            if bar.open <= target:
                exit_price, reason, exit_index = target, "target_gap", cursor
                break
            if bar.high >= stop:
                exit_price, reason, exit_index = stop, "sl", cursor
                break
            if bar.low <= target:
                exit_price, reason, exit_index = target, "tp", cursor
                break
    raw_return = side * (exit_price - fill) / fill - (1.5 * pip) / fill
    risk = risk_distance / fill
    return {
        "account_return": 0.005 * (raw_return / risk if risk else 0),
        "reason": reason, "exit_index": exit_index, "fill": fill, "actual_rr": actual_rr,
    }


def simulate_one_position_at_a_time(raw, candidates, pip):
    trades = []
    last_exit_index = -1
    for signal in sorted(candidates, key=lambda row: row["signal_close_utc"]):
        entry_index = raw.index.searchsorted(pd.Timestamp(signal["signal_close_utc"]), side="left")
        if entry_index <= last_exit_index:
            continue
        trade = simulate(raw, signal, pip)
        if trade is None:
            continue
        last_exit_index = trade["exit_index"]
        trades.append({**signal, **trade})
    return trades


def _performance(returns):
    wins = [value for value in returns if value > 0]
    losses = [value for value in returns if value < 0]
    equity = 1.0
    peak = 1.0
    drawdown = 0.0
    for value in returns:
        equity *= 1 + value
        peak = max(peak, equity)
        drawdown = max(drawdown, (peak - equity) / peak)
    return {
        "trades": len(returns), "wins": len(wins), "losses": len(returns) - len(wins),
        "win_rate": len(wins) / len(returns) if returns else 0,
        "profit_factor": (sum(wins) / abs(sum(losses)) if losses
                          else (float("inf") if wins else 0)),
        "return_pct": (equity - 1) * 100, "max_drawdown_pct": drawdown * 100,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    cache = ROOT / "backtest" / "forex_test_data"
    results = []
    base_options = strategy_config(load_config())
    raw_by_pair = {pair: fetch(pair, args.days, cache, args.refresh) for pair, _ in CASES}
    candidates_by_pair_variant = {}
    for case in CASES:
        raw = raw_by_pair[case["pair"]]
        candidates = signals(raw, case["variant"], base_options)
        candidates_by_pair_variant[(case["pair"], case["variant"])] = candidates
        pip = PAIRS[case["pair"]][1]
        trades = [trade for candidate in candidates
                  if (trade := simulate(raw, candidate, pip))]
        summary = _performance([trade["account_return"] for trade in trades])
        results.append({**case, "data_days": args.days, "bars_5m": len(raw),
                        **summary})

    pair_results = []
    pair_audit = []
    for pair in sorted({case["pair"] for case in CASES}):
        raw = raw_by_pair[pair]
        by_variant = {
            case["variant"]: candidates_by_pair_variant[(pair, case["variant"])]
            for case in CASES if case["pair"] == pair
        }
        selected, audit = select_pair_candidates(pair, by_variant)
        pair_audit.extend(audit)
        trades = simulate_one_position_at_a_time(raw, selected, PAIRS[pair][1])
        performance = _performance([trade["account_return"] for trade in trades])
        pair_results.append({
            "pair": pair, "registered_variants": ";".join(by_variant),
            "candidate_signals": sum(map(len, by_variant.values())),
            "selected_opportunities": len(selected),
            "conflicts": sum(row["status"] == "CONFLICT" for row in audit),
            "one_position_at_a_time": True,
            **performance,
        })

    variant_path = ROOT / "backtest" / "original_forex_variants_7d_results.csv"
    pair_path = ROOT / "backtest" / "original_pair_selected_7d_results.csv"
    audit_path = ROOT / "backtest" / "original_pair_selection_audit.json"
    pd.DataFrame(results).to_csv(variant_path, index=False)
    pd.DataFrame(pair_results).to_csv(pair_path, index=False)
    pd.DataFrame(pair_audit).to_json(audit_path, orient="records", indent=2)
    print(pd.DataFrame(results).to_string(index=False))
    print("\nPair-level runs using the live selector:")
    print(pd.DataFrame(pair_results).to_string(index=False))
    print(f"Saved {variant_path}, {pair_path}, and {audit_path}")


if __name__ == "__main__":
    main()
