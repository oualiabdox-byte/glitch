#!/usr/bin/env python3
"""Run the isolated Auction/Mean-Reversion Strategy B on stored 14d M5 data."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from strategy.auction_mean_reversion import AuctionConfig, backtest_pair

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "backtest" / "ctrader_volume_data"
OUT_DIR = ROOT / "backtest" / "auction_mean_reversion_14d"
PAIRS = ("AUDUSD", "EURUSD", "GBPUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY")
BASELINE_VERSION = "B-v1"
BASELINE_SOURCE_COMMIT = "444b9f6c11a5ba0cc4979b954b97682423cec0b0"


def metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(row["net_R"]) for row in trades]
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    gross_profit, gross_loss = sum(wins), abs(sum(losses))
    equity, peak, max_dd = 0.0, 0.0, 0.0
    # Aggregate trades are appended pair-by-pair; sort by exit time before
    # computing the diagnostic R drawdown so pair grouping cannot skew it.
    chronological = sorted(trades, key=lambda row: row["exit_time_utc"])
    for trade in chronological:
        value = float(trade["net_R"])
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return {
        "trades": len(values),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": 100 * len(wins) / len(values) if values else None,
        "profit_factor": gross_profit / gross_loss if gross_loss else None,
        "gross_R": sum(float(row["gross_R"]) for row in trades),
        "cost_R": sum(float(row["cost_R"]) for row in trades),
        "net_R": sum(values),
        "average_net_R": sum(values) / len(values) if values else None,
        "max_drawdown_R": max_dd,
        "average_planned_RR": (sum(float(row["planned_rr"]) for row in trades) / len(trades)
                                if trades else None),
    }


def load_rows(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = sorted(payload["candles"], key=lambda row: row["time"])
    if not rows:
        raise ValueError(f"No candles in {path}")
    for row in rows:
        for key in ("open", "high", "low", "close"):
            row[key] = float(row[key])
        if row["high"] < max(row["open"], row["close"]) or row["low"] > min(row["open"], row["close"]):
            raise ValueError(f"Invalid OHLC candle in {path}: {row}")
    return payload, rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    config = AuctionConfig()
    all_trades: list[dict[str, Any]] = []
    pair_metrics: dict[str, Any] = {}
    data_window: dict[str, Any] = {}
    for pair in PAIRS:
        source = DATA_DIR / f"{pair}_m5_14d.json"
        payload, rows = load_rows(source)
        trades = backtest_pair(pair, rows, config)
        all_trades.extend(trades)
        pair_metrics[pair] = metrics(trades)
        data_window[pair] = {
            "source_dataset": payload.get("source_dataset"),
            "bars": len(rows),
            "start_utc": rows[0]["time"],
            "end_utc": rows[-1]["time"],
        }

    summary = {
        "experiment": "Strategy B-v1 — Auction / Mean-Reversion",
        "version": BASELINE_VERSION,
        "baseline_status": "FROZEN_BASELINE",
        "frozen_source_commit": BASELINE_SOURCE_COMMIT,
        "pair_universe_policy": "All seven pairs retained; no post-hoc pair exclusions.",
        "source_note": "Existing repository cTrader M5 OHLC + trendbar-volume datasets named 14d; no new or simulated market data.",
        "strategy_note": "Independent of canonical H1 POI/FVG/OB continuation logic; rolling 24h range extreme -> previous-hour liquidity sweep/rejection -> close beyond prior three-bar pivot -> next M5 open; target frozen 24h range midpoint.",
        "controls": {
            "value_fraction": config.value_fraction,
            "range_lookback_bars": config.range_lookback_bars,
            "liquidity_lookback_bars": config.liquidity_lookback_bars,
            "choch_lookback_bars": config.choch_lookback_bars,
            "pending_expiry_bars": config.pending_expiry_bars,
            "stop_atr_buffer": config.stop_atr_buffer,
            "min_stop_buffer_pips": config.min_stop_buffer_pips,
            "min_reward_risk": config.min_reward_risk,
            "max_holding_bars": config.max_holding_bars,
            "round_turn_cost_pips": config.round_turn_cost_pips,
            "entry": "next M5 open after confirmation",
            "intrabar_policy": "gap-aware; stop-first when stop and target are both touched in one OHLC bar",
            "position_rule": "one open position per pair; no portfolio leverage or allocation overlay",
        },
        "data": data_window,
        "aggregate_metrics": metrics(all_trades),
        "pair_metrics": pair_metrics,
        "caution": "14-day research sample only; OHLC cannot establish intrabar order, spreads/slippage vary, the fixed cost is approximate, and these results are not profitability evidence or a recommendation to enable live trading.",
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(OUT_DIR / "trades.csv", all_trades)
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Strategy B-v1: Auction / Mean-Reversion — 14-day repository dataset",
        "",
        f"> **Frozen raw baseline.** Source commit `{BASELINE_SOURCE_COMMIT}`. Strategy A and the B-v1 rules remain unchanged; future variants must use separate versioned implementations and output directories.",
        "",
        "summary[\"strategy_note\"]",
        "",
        "## Locked rules and execution controls",
        "",
        "- Use only the prior 288 completed M5 bars to define the rolling 24-hour auction range and midpoint.",
        "- Long setup: close back above the prior 12-bar low after sweeping it, at the lower 15% of that range, with bullish rejection.",
        "- Short setup: close back below the prior 12-bar high after sweeping it, at the upper 15% of that range, with bearish rejection.",
        "- Confirm within six bars with a directional close beyond the preceding three-bar pivot; enter at the next M5 open.",
        "- Stop beyond the sweep extreme by max(0.1 x ATR(14), 0.5 pip); target is the range midpoint frozen at sweep; require planned reward/risk >= 1.0.",
        "- One position per pair, maximum 24-hour hold, 1.5-pip round-turn cost, and stop-first handling for ambiguous same-bar stop/target touches.",
        "",
        "## Aggregate results",
        "",
        "| Metric | Result |",
        "|---|---:|",
    ]
    aggregate = summary["aggregate_metrics"]
    for key, label in (("trades", "Trades"), ("wins", "Wins"), ("losses", "Losses"),
                       ("win_rate_pct", "Win rate (%)"), ("profit_factor", "Profit factor"),
                       ("gross_R", "Gross R"), ("cost_R", "Estimated cost (R)"),
                       ("net_R", "Net R after cost"), ("average_net_R", "Average net R/trade"),
                       ("max_drawdown_R", "Max drawdown (R)"), ("average_planned_RR", "Mean planned R:R")):
        value = aggregate[key]
        formatted = "n/a" if value is None else (str(value) if isinstance(value, int) else f"{value:.4f}")
        lines.append(f"| {label} | {formatted} |")
    lines += ["", "## Per-pair results", "", "| Pair | Bars | Trades | Win rate (%) | PF | Net R | Max DD (R) |", "|---|---:|---:|---:|---:|---:|---:|"]
    for pair in PAIRS:
        item = pair_metrics[pair]
        values = (data_window[pair]["bars"], item["trades"], item["win_rate_pct"], item["profit_factor"], item["net_R"], item["max_drawdown_R"])
        formatted = [str(values[0]), str(values[1])] + ["n/a" if value is None else f"{value:.4f}" for value in values[2:]]
        lines.append(f"| {pair} | " + " | ".join(formatted) + " |")
    lines += ["", "## Data coverage", "", "| Pair | Bars | Start UTC | End UTC |", "|---|---:|---|---|"]
    for pair in PAIRS:
        item = data_window[pair]
        lines.append(f"| {pair} | {item['bars']} | {item['start_utc']} | {item['end_utc']} |")
    lines += [
        "",
        "## Interpretation limits",
        "",
        summary["caution"],
        "",
        "The aggregate sums each trade in R and is not a portfolio-equity curve: simultaneous exposure and cross-pair correlation are not modeled. This short sample was not used to tune the locked rules.",
        "",
        "Trade-level audit: `trades.csv`; machine-readable results: `summary.json`; frozen specification and input hashes: `v1_baseline.json`.",
        "",
    ]
    (OUT_DIR / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
