#!/usr/bin/env python3
"""Compare equal-weight execution with volume-cycle allocation on cTrader M5.

The canonical strategy and selector are imported unchanged. This harness only
adds data preparation, M5 execution simulation, portfolio allocation, and
reporting. With M5-only data, entries use the next M5 open and the existing
``sl_first`` policy is applied to M5 OHLC bars.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from concurrent.futures import ProcessPoolExecutor, as_completed
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from config.settings import load_config, strategy_config, risk_config
from strategy import build_variant, select_signals, signal_identity, variants_for_pair
from strategy.volume_cycle_allocator import AdaptiveAllocator, AllocatorConfig, VolumeCycle, build_volume_cycles

ROOT = Path(__file__).resolve().parents[1]
PAIRS = ("AUDUSD", "EURUSD", "GBPUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY")
PIP = 0.0001
RISK_PER_TRADE = 0.005
ROUND_TURN_COST_PIPS = 1.5
MAX_OPEN_POSITIONS = 3
CYCLE_CONFIG = AllocatorConfig(target_cycle_bars=96, volume_lookback_bars=96, warmup_bars=96, history_cycles=6)


@dataclass
class OpenTrade:
    signal: dict[str, Any]
    pair: str
    side: int
    fill: float
    risk_distance: float
    weight: float
    entry_time: str
    current_stop: float | None = None
    best_favorable: float = 0.0
    exit_time: str | None = None
    exit_price: float | None = None
    exit_reason: str | None = None


def _rows(frame: pd.DataFrame, include_volume: bool = False) -> list[dict[str, Any]]:
    result = []
    for ts, row in frame.iterrows():
        item = {"time": ts.isoformat(), "open": float(row.open), "high": float(row.high), "low": float(row.low), "close": float(row.close)}
        if include_volume:
            item["volume"] = float(row.volume)
        result.append(item)
    return result


def _load_pair(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    payload = json.loads(path.read_text())
    rows = payload["candles"]
    frame = pd.DataFrame(rows)
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    frame = frame.sort_values("time").drop_duplicates("time").set_index("time")
    frame = frame[["open", "high", "low", "close", "volume"]].astype(float)
    grouped = frame.resample("1h", label="left", closed="left")
    h1 = grouped.agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    counts = grouped["close"].count()
    h1 = h1.loc[counts == 12].dropna()
    if len(frame) < 100 or len(h1) < 20:
        raise RuntimeError(f"{path.name}: insufficient M5/H1 data ({len(frame)}/{len(h1)})")
    return frame, h1


def _signal_from_decision(pair: str, variant: str, signal_close: pd.Timestamp, decision: Any) -> dict[str, Any] | None:
    if not decision.is_signal:
        return None
    evidence = decision.evidence
    event = evidence.get("m5_bos", {})
    event_time = event.get("time")
    if not event_time:
        return None
    signal = {
        "pair": pair,
        "variant": variant,
        "signal_close_utc": signal_close.isoformat(),
        "event_time_utc": pd.Timestamp(event_time).tz_localize("UTC").isoformat() if pd.Timestamp(event_time).tzinfo is None else pd.Timestamp(event_time).tz_convert("UTC").isoformat(),
        "side": "LONG" if decision.side == "LONG" else "SHORT",
        "entry_reference": float(decision.entry_price),
        "stop": float(decision.stop_price),
        "target": float(decision.target_price),
        "planned_rr": float(decision.risk_reward or 0.0),
        "evidence": evidence,
    }
    signal["signal_id"] = signal_identity(signal)
    return signal


def collect_variant_signals(pair: str, variant: str, m5: pd.DataFrame, h1: pd.DataFrame) -> list[dict[str, Any]]:
    cfg = strategy_config(load_config())
    strategy = build_variant(variant, base_options=cfg)
    h1_rows = _rows(h1)
    m5_rows = _rows(m5, include_volume=True)
    h1_closes = h1.index + pd.Timedelta(hours=1)
    seen_events: set[str] = set()
    setup_state = None
    output: list[dict[str, Any]] = []
    for i in range(len(m5_rows)):
        signal_close = m5.index[i] + pd.Timedelta(minutes=5)
        h1_right = int(h1_closes.searchsorted(signal_close, side="right"))
        if h1_right < 20:
            continue
        recent_h1 = h1_rows[:h1_right]
        decision = strategy.evaluate(recent_h1, m5_rows[:i + 1], setup_state=setup_state)
        evidence = decision.evidence
        structure = evidence.get("h1_structure", {})
        poi = evidence.get("h1_poi", {})
        lifecycle = evidence.get("poi_state", {})
        if structure.get("side") and structure.get("last_event") and poi:
            setup_state = {
                "side": structure["side"], "h1_structure": structure, "h1_poi": poi,
                "poi_formed_time": lifecycle.get("poi_formed_time"), "poi_touch_time": lifecycle.get("poi_touch_time"),
                "poi_active": lifecycle.get("poi_active", False), "confirmation_invalidated": lifecycle.get("confirmation_invalidated", False),
                "target_invalidated": lifecycle.get("target_invalidated", False), "invalidated_at": lifecycle.get("invalidated_at"),
                "status": lifecycle.get("status", "IDENTIFIED"), "updated_at": signal_close.isoformat(),
            }
        else:
            setup_state = None
        signal = _signal_from_decision(pair, variant, signal_close, decision)
        if signal and signal["event_time_utc"] not in seen_events:
            seen_events.add(signal["event_time_utc"])
            output.append(signal)
    return output


def select_pair_opportunities(pair: str, candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    expected = variants_for_pair(pair) or ("config_default",)
    by_close: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        by_close[str(candidate["signal_close_utc"])].append(candidate)
    selected: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    for close_time in sorted(by_close):
        at_close = by_close[close_time]
        present = {str(row["variant"]) for row in at_close}
        results = [{**row, "status": "SIGNAL_ONLY"} for row in at_close]
        results.extend({"pair": pair, "variant": name, "status": "NO_TRADE"} for name in expected if name not in present)
        decision = select_signals(results, expected_variants=expected)
        winning = decision.get("selected_signal")
        if winning:
            selected.append({key: value for key, value in winning.items() if key != "status"})
        audit.append({
            "pair": pair, "signal_close_utc": close_time, "status": decision["status"],
            "selected_variant": winning.get("variant") if winning else None,
            "selected_signal_id": decision.get("selected_signal_id"),
            "candidate_signal_ids": json.dumps(decision.get("candidate_signal_ids", [])),
            "conflict": json.dumps(decision.get("conflict"), sort_keys=True),
        })
    return selected, audit


def _exit_for_bar(trade: OpenTrade, bar: pd.Series) -> tuple[float, str] | None:
    stop = float(trade.current_stop if trade.current_stop is not None else trade.signal["stop"])
    target = float(trade.signal["target"])
    opened, high, low = float(bar.open), float(bar.high), float(bar.low)
    if trade.side == 1:
        if opened <= stop:
            return opened, "stop_gap"
        if opened >= target:
            return target, "target_gap"
        if low <= stop:
            return stop, "stop"
        if high >= target:
            return target, "target"
    else:
        if opened >= stop:
            return opened, "stop_gap"
        if opened <= target:
            return target, "target_gap"
        if high >= stop:
            return stop, "stop"
        if low <= target:
            return target, "target"
    return None


def _metrics(trades: list[dict[str, Any]], equity_curve: list[float]) -> dict[str, Any]:
    values = [float(t["net_R"]) for t in trades]
    weighted = [float(t["weighted_R"]) for t in trades]
    wins = [v for v in values if v > 0]
    losses = [v for v in values if v < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    peak = 1.0
    max_dd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        max_dd = max(max_dd, 1 - value / peak)
    return {
        "total_trades": len(trades),
        "wins": len(wins), "losses": len(losses),
        "win_rate_pct": len(wins) / len(values) * 100 if values else None,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "total_R_raw": sum(values), "total_R_weighted": sum(weighted),
        "average_R_raw": sum(values) / len(values) if values else None,
        "average_R_weighted": sum(weighted) / len(weighted) if weighted else None,
        "return_pct": (equity_curve[-1] - 1) * 100 if equity_curve else 0.0,
        "max_DD_pct": max_dd * 100,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fields = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run_portfolio(
    name: str,
    pairs: list[str],
    frames: dict[str, pd.DataFrame],
    signals: list[dict[str, Any]],
    cycles_by_pair: dict[str, list[VolumeCycle]],
    weights_initial: dict[str, float],
    adaptive: bool,
    signal_multipliers: dict[str, float] | None = None,
    dynamic_stop_mode: str | None = None,
) -> dict[str, Any]:
    timeline = sorted(set.union(*(set(frames[pair].index) for pair in pairs)))
    by_entry: dict[pd.Timestamp, list[dict[str, Any]]] = defaultdict(list)
    for signal in signals:
        entry_time = pd.Timestamp(signal["signal_close_utc"])
        next_bar = frames[signal["pair"]].index.searchsorted(entry_time, side="left")
        if next_bar < len(frames[signal["pair"]].index):
            signal = {**signal, "entry_time": frames[signal["pair"]].index[next_bar].isoformat()}
            by_entry[frames[signal["pair"]].index[next_bar]].append(signal)
        else:
            signal = {**signal, "skip_reason": "no_future_bar"}
    allocator = AdaptiveAllocator(pairs, CYCLE_CONFIG)
    weights = dict(weights_initial)
    active: dict[str, OpenTrade] = {}
    trades: list[dict[str, Any]] = []
    skipped: dict[str, int] = defaultdict(int)
    valid_opportunities = 0
    equity = 1.0
    equity_curve = [equity]
    exposure_rows: list[dict[str, Any]] = []
    cycle_events = sorted(
        ((cycle.end_time, cycle) for cycles in cycles_by_pair.values() for cycle in cycles),
        key=lambda item: (item[0], item[1].pair, item[1].cycle_id),
    )
    cycle_cursor = 0
    cycle_rankings: list[dict[str, Any]] = []
    turnover = 0.0
    performance_by_cycle: list[dict[str, Any]] = []
    last_cycle_equity = equity
    event_id = 0
    rolling_rows: list[dict[str, Any]] = []
    last_equity_by_trade = equity

    for timestamp in timeline:
        # Close existing positions on the current M5 OHLC bar.
        for pair in list(active):
            if timestamp not in frames[pair].index:
                continue
            trade = active[pair]
            if dynamic_stop_mode:
                if dynamic_stop_mode not in {"BE_1R", "TRAIL_1R", "TRAIL_1_5R"}:
                    raise ValueError(f"unknown dynamic_stop_mode: {dynamic_stop_mode}")
                if dynamic_stop_mode in {"BE_1R", "TRAIL_1R"} and trade.best_favorable >= trade.risk_distance:
                    if trade.side == 1:
                        trade.current_stop = max(float(trade.current_stop), trade.fill if dynamic_stop_mode == "BE_1R" else trade.fill + 0.25 * trade.risk_distance)
                    else:
                        trade.current_stop = min(float(trade.current_stop), trade.fill if dynamic_stop_mode == "BE_1R" else trade.fill - 0.25 * trade.risk_distance)
                if dynamic_stop_mode in {"TRAIL_1R", "TRAIL_1_5R"} and trade.best_favorable >= (1.0 if dynamic_stop_mode == "TRAIL_1R" else 1.5) * trade.risk_distance:
                    if trade.side == 1:
                        trade.current_stop = max(float(trade.current_stop), trade.fill + 0.75 * trade.risk_distance)
                    else:
                        trade.current_stop = min(float(trade.current_stop), trade.fill - 0.75 * trade.risk_distance)
            result = _exit_for_bar(trade, frames[pair].loc[timestamp])
            if result is None:
                bar = frames[pair].loc[timestamp]
                favorable = (float(bar.high) - trade.fill) if trade.side == 1 else (trade.fill - float(bar.low))
                trade.best_favorable = max(trade.best_favorable, favorable)
                continue
            trade = active.pop(pair)
            trade.exit_time = timestamp.isoformat()
            trade.exit_price, trade.exit_reason = result
            gross_pnl = trade.side * (trade.exit_price - trade.fill)
            gross_r = gross_pnl / trade.risk_distance
            cost_price = ROUND_TURN_COST_PIPS * PIP
            net_r = (gross_pnl - cost_price) / trade.risk_distance
            weighted_r = trade.weight * net_r
            account_return = RISK_PER_TRADE * weighted_r
            equity *= 1 + account_return
            row = {
                "portfolio": name, "pair": pair, "variant": trade.signal["variant"], "signal_id": trade.signal["signal_id"],
                "signal_close_utc": trade.signal["signal_close_utc"], "entry_time_utc": trade.entry_time,
                "exit_time_utc": trade.exit_time, "side": trade.signal["side"], "fill": trade.fill,
                "stop": trade.signal["stop"], "dynamic_stop_at_exit": trade.current_stop, "target": trade.signal["target"], "exit_price": trade.exit_price,
                "exit_reason": trade.exit_reason, "risk_distance": trade.risk_distance, "gross_R": gross_r,
                "net_R": net_r, "allocation_weight": trade.weight, "weighted_R": weighted_r,
                "account_return_pct": account_return * 100, "equity_after": equity,
            }
            trades.append(row)
            last_equity_by_trade = equity
            window = trades[-20:]
            rolling_rows.append({"portfolio": name, "trade_index": len(trades), "exit_time_utc": trade.exit_time,
                                 "rolling_trades": len(window), "rolling_total_R_weighted": sum(float(x["weighted_R"]) for x in window),
                                 "rolling_return_pct": (equity / (float(window[0]["equity_after"]) / (1 + RISK_PER_TRADE * float(window[0]["weighted_R"]))) - 1) * 100 if window else 0.0})

        # Enter selected signals at next M5 open.
        for signal in by_entry.get(timestamp, []):
            pair = signal["pair"]
            if pair in active:
                skipped["position_open"] += 1
                continue
            if len(active) >= MAX_OPEN_POSITIONS:
                skipped["max_open_positions"] += 1
                continue
            bar = frames[pair].loc[timestamp]
            fill = float(bar.open)
            side = 1 if signal["side"] == "LONG" else -1
            stop, target = float(signal["stop"]), float(signal["target"])
            if (side == 1 and not stop < fill < target) or (side == -1 and not target < fill < stop):
                skipped["invalid_fill"] += 1
                continue
            valid_opportunities += 1
            multiplier = float((signal_multipliers or {}).get(signal["signal_id"], 1.0))
            allocation_weight = weights[pair] * multiplier
            if adaptive and allocation_weight <= 1e-12:
                skipped["zero_allocator_weight"] += 1
                continue
            active[pair] = OpenTrade(signal=signal, pair=pair, side=side, fill=fill,
                                     risk_distance=abs(fill - stop), weight=allocation_weight,
                                     entry_time=timestamp.isoformat(), current_stop=stop)

        # A cycle can affect allocations only after the bar that completed it.
        while cycle_cursor < len(cycle_events) and pd.Timestamp(cycle_events[cycle_cursor][0]) <= timestamp:
            end_time, cycle = cycle_events[cycle_cursor]
            allocator.record_completed_cycle(cycle)
            if adaptive:
                new_weights = allocator.weights()
                turnover += sum(abs(new_weights[pair] - weights[pair]) for pair in pairs) / 2
                weights = new_weights
            ranked = sorted(((pair, weights[pair]) for pair in pairs), key=lambda item: (-item[1], item[0]))
            event_id += 1
            cycle_rankings.append({"cycle_event_id": event_id, "cycle_end_utc": end_time, "trigger_pair": cycle.pair,
                                   "trigger_cycle_id": cycle.cycle_id,
                                   "ranking": " > ".join(f"{pair}:{weight:.6f}" for pair, weight in ranked),
                                   **{f"weight_{pair}": weights[pair] for pair in pairs}})
            performance_by_cycle.append({"portfolio": name, "cycle_event_id": event_id, "cycle_end_utc": end_time,
                                         "trigger_pair": cycle.pair, "trigger_cycle_id": cycle.cycle_id,
                                         "equity": equity, "cycle_return_pct": (equity / last_cycle_equity - 1) * 100})
            last_cycle_equity = equity
            cycle_cursor += 1

        exposure = sum(trade.weight for trade in active.values())
        exposure_rows.append({"portfolio": name, "time": timestamp.isoformat(), "active_positions": len(active),
                              "exposure": exposure, "capital_utilization": exposure,
                              **{f"weight_{pair}": weights[pair] for pair in pairs}})
        equity_curve.append(equity)

    # Mark open positions at the final available close using the same close-only convention as existing backtests.
    if timeline:
        last_time = timeline[-1]
        for pair, trade in active.items():
            close = float(frames[pair].loc[last_time].close)
            gross_r = trade.side * (close - trade.fill) / trade.risk_distance
            net_r = (trade.side * (close - trade.fill) - ROUND_TURN_COST_PIPS * PIP) / trade.risk_distance
            trades.append({"portfolio": name, "pair": pair, "variant": trade.signal["variant"], "signal_id": trade.signal["signal_id"],
                           "signal_close_utc": trade.signal["signal_close_utc"], "entry_time_utc": trade.entry_time,
                           "exit_time_utc": last_time.isoformat(), "side": trade.signal["side"], "fill": trade.fill,
                           "stop": trade.signal["stop"], "target": trade.signal["target"], "exit_price": close,
                           "exit_reason": "end_of_sample_mark", "risk_distance": trade.risk_distance, "gross_R": gross_r,
                           "net_R": net_r, "allocation_weight": trade.weight, "weighted_R": trade.weight * net_r,
                           "account_return_pct": RISK_PER_TRADE * trade.weight * net_r * 100,
                           "equity_after": equity})
            skipped["open_at_end_marked"] += 1

    return {
        "name": name, "trades": trades, "skipped": dict(skipped), "valid_opportunities": valid_opportunities,
        "equity_curve": equity_curve, "exposure_rows": exposure_rows, "cycle_rankings": cycle_rankings,
        "performance_by_cycle": performance_by_cycle, "rolling_rows": rolling_rows,
        "turnover_one_way": turnover, "metrics": _metrics(trades, equity_curve),
    }


def _report(summary: dict[str, Any], path: Path) -> None:
    lines = [f"# {summary.get('data_suffix', 'unknown')} cTrader M5 Strategy / Allocation Comparison", "",
             "> The canonical strategy, selector, entry/SL/TP values, 1.5-pip cost, and conservative `sl_first` intrabar policy are unchanged. This is a short research sample, not a profitability claim.", "",
             "## Data and controls", "",
             f"- Pairs: {', '.join(summary['pairs'])}",
             f"- Common M5 bars: {summary['common_m5_bars']}",
             f"- Simulation timeline bars (union across pairs): {summary['simulation_timeline_bars']}",
             f"- Period: {summary['first_timestamp']} to {summary['last_timestamp']}",
             "- Source: cTrader M5 OHLC plus native trendbar volume.",
             "- Entry: next available M5 open after the signal close.",
             "- Risk budget: 0.5% of each pair sleeve; maximum three concurrent positions and one position per pair.",
             "- Equal Weight: 1/7 sleeve weight for every pair.",
             "- Adaptive: Volume-Cycle weights held from cycle completion until the next completed cycle; zero-weight signals are counted as skipped valid opportunities.",
             "", "## Headline comparison", "",
             "| Metric | Existing / Equal Weight | Volume-Cycle Adaptive |", "|---|---:|---:|"]
    for key, label in [("total_trades", "Total trades"), ("win_rate_pct", "Win rate %"), ("profit_factor", "PF"), ("total_R_raw", "Total R (raw)"), ("total_R_weighted", "Total R (weighted)"), ("return_pct", "Return %"), ("max_DD_pct", "Max DD %"), ("average_R_raw", "Average R (raw)"), ("average_R_weighted", "Average R (weighted)"), ("average_exposure_pct", "Average exposure %"), ("capital_utilization_pct", "Capital utilization %"), ("skipped_valid_opportunities", "Skipped valid opportunities"), ("best_cycle_return_pct", "Best cycle %"), ("worst_cycle_return_pct", "Worst cycle %")]:
        a, b = summary["equal_weight"][key], summary["adaptive"][key]
        fmt = lambda x: "n/a" if x is None else f"{x:.6f}" if isinstance(x, float) else str(x)
        lines.append(f"| {label} | {fmt(a)} | {fmt(b)} |")
    lines += ["", "## Allocation diagnostics", "", f"- Completed volume cycles: {summary['completed_volume_cycles']}",
              f"- Equal-weight turnover: {summary['equal_weight']['turnover_one_way']:.6f}",
              f"- Adaptive turnover (one-way): {summary['adaptive']['turnover_one_way']:.6f}"]
    for portfolio in ("equal_weight", "adaptive"):
        data = summary[portfolio]
        lines += [f"- {portfolio}: average exposure {data['average_exposure_pct']:.4f}%, max exposure {data['max_exposure_pct']:.4f}%, capital utilization {data['capital_utilization_pct']:.4f}%.",
                  f"- {portfolio}: skipped valid opportunities {data['skipped_valid_opportunities']}."]
    lines += ["", "## Output files", "", "- `trades_equal_weight.csv` and `trades_adaptive.csv` contain the full fills/exits.", "- `cycle_rankings.csv` contains pair ranking and allocation weight at each completed volume-cycle event.", "- `performance_by_cycle.csv` contains performance segmented by cycle event.", "- `rolling_performance.csv` contains rolling 20-trade weighted R and return.", "- `allocation_weights.csv` contains time-series pair sleeve weights and exposure."]
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("backtest/ctrader_volume_data"))
    parser.add_argument("--output-dir", type=Path, default=Path("backtest/ctrader_allocator_24d_comparison"))
    parser.add_argument("--data-suffix", default="24d", help="Dataset filename suffix, e.g. 10d or 24d")
    args = parser.parse_args()
    frames: dict[str, pd.DataFrame] = {}
    volume_rows: dict[str, list[dict[str, Any]]] = {}
    for pair in PAIRS:
        path = args.data_dir / f"{pair}_m5_{args.data_suffix}.json"
        frame, h1 = _load_pair(path)
        frames[pair] = frame
        volume_rows[pair] = _rows(frame, include_volume=True)
    common = sorted(set.intersection(*(set(frames[pair].index) for pair in PAIRS)))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    candidates_by_pair: dict[str, list[dict[str, Any]]] = {}
    selected_by_pair: dict[str, list[dict[str, Any]]] = {}
    audits: list[dict[str, Any]] = []
    signal_cache = args.output_dir / "signal_cache.json"
    if signal_cache.exists():
        cached = json.loads(signal_cache.read_text())
        candidates_by_pair = cached["candidates_by_pair"]
        selected_by_pair = cached["selected_by_pair"]
        audits = cached["audits"]
        print(f"Loaded signal cache: {sum(len(v) for v in selected_by_pair.values())} selected opportunities", flush=True)
    else:
        futures = {}
        with ProcessPoolExecutor(max_workers=min(8, sum(len(variants_for_pair(pair) or ("config_default",)) for pair in PAIRS))) as pool:
            for pair in PAIRS:
                frame, h1 = _load_pair(args.data_dir / f"{pair}_m5_{args.data_suffix}.json")
                variants = variants_for_pair(pair) or ("config_default",)
                for variant in variants:
                    print(f"Queueing {pair}/{variant}", flush=True)
                    future = pool.submit(collect_variant_signals, pair, variant, frame, h1)
                    futures[future] = (pair, variant)
            for future in as_completed(futures):
                pair, variant = futures[future]
                candidates_by_pair.setdefault(pair, []).extend(future.result())
                print(f"Finished {pair}/{variant}", flush=True)
        for pair in PAIRS:
            all_candidates = candidates_by_pair.get(pair, [])
            selected, audit = select_pair_opportunities(pair, all_candidates)
            selected_by_pair[pair] = selected
            audits.extend(audit)
            print(f"  {pair}: {len(all_candidates)} candidates -> {len(selected)} selected", flush=True)
        signal_cache.write_text(json.dumps({"candidates_by_pair": candidates_by_pair, "selected_by_pair": selected_by_pair, "audits": audits}, indent=2) + "\n")
    selected_signals = [signal for values in selected_by_pair.values() for signal in values]
    cycles_by_pair = {pair: build_volume_cycles(pair, volume_rows[pair], CYCLE_CONFIG) for pair in PAIRS}
    completed_cycles = sum(len(value) for value in cycles_by_pair.values())
    equal_weights = {pair: 1.0 / len(PAIRS) for pair in PAIRS}
    equal = run_portfolio("equal_weight", list(PAIRS), frames, selected_signals, cycles_by_pair, equal_weights, adaptive=False)
    adaptive = run_portfolio("adaptive", list(PAIRS), frames, selected_signals, cycles_by_pair, equal_weights, adaptive=True)

    for result in (equal, adaptive):
        exposure = [float(row["exposure"]) for row in result["exposure_rows"]]
        cycle_returns = [float(row["cycle_return_pct"]) for row in result["performance_by_cycle"]]
        metrics = result["metrics"]
        metrics["skipped_valid_opportunities"] = result["skipped"].get("position_open", 0) + result["skipped"].get("max_open_positions", 0) + result["skipped"].get("zero_allocator_weight", 0)
        metrics["average_exposure_pct"] = sum(exposure) / len(exposure) * 100 if exposure else 0.0
        metrics["max_exposure_pct"] = max(exposure) * 100 if exposure else 0.0
        metrics["capital_utilization_pct"] = metrics["average_exposure_pct"]
        metrics["turnover_one_way"] = result["turnover_one_way"]
        metrics["skipped_counts"] = result["skipped"]
        metrics["best_cycle_return_pct"] = max(cycle_returns) if cycle_returns else None
        metrics["worst_cycle_return_pct"] = min(cycle_returns) if cycle_returns else None
    simulation_timeline = sorted(set.union(*(set(frames[pair].index) for pair in PAIRS)))
    summary = {
        "data_suffix": args.data_suffix, "pairs": list(PAIRS), "common_m5_bars": len(common), "simulation_timeline_bars": len(simulation_timeline), "first_timestamp": common[0].isoformat(), "last_timestamp": common[-1].isoformat(),
        "completed_volume_cycles": completed_cycles, "selected_opportunities": len(selected_signals),
        "strategy_unchanged": True, "cost_pips_round_turn": ROUND_TURN_COST_PIPS, "intrabar_policy": "sl_first", "max_open_positions": MAX_OPEN_POSITIONS,
        "risk_per_trade_pct": RISK_PER_TRADE * 100, "cycle_config": CYCLE_CONFIG.__dict__,
        "equal_weight": equal["metrics"], "adaptive": adaptive["metrics"],
        "selector_audit_rows": len(audits),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (args.output_dir / "selection_audit.json").write_text(json.dumps(audits, indent=2) + "\n")
    _write_csv(args.output_dir / "trades_equal_weight.csv", equal["trades"])
    _write_csv(args.output_dir / "trades_adaptive.csv", adaptive["trades"])
    _write_csv(args.output_dir / "cycle_rankings.csv", adaptive["cycle_rankings"])
    _write_csv(args.output_dir / "performance_by_cycle.csv", adaptive["performance_by_cycle"] + equal["performance_by_cycle"])
    _write_csv(args.output_dir / "rolling_performance.csv", adaptive["rolling_rows"] + equal["rolling_rows"])
    weight_rows = []
    for row in adaptive["exposure_rows"]:
        weight_rows.append(row)
    _write_csv(args.output_dir / "allocation_weights.csv", weight_rows)
    _report(summary, args.output_dir / "report.md")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
