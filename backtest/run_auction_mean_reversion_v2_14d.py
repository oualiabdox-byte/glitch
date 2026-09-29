#!/usr/bin/env python3
"""Run preregistered Strategy B-v2 on the same 14d FX data as frozen B-v1."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backtest.run_auction_mean_reversion_14d import (
    DATA_DIR,
    OUT_DIR as B1_OUT_DIR,
    PAIRS,
    load_rows,
    metrics,
    write_csv,
)
from strategy.auction_mean_reversion import AuctionConfig
from strategy.auction_mean_reversion_v2 import (
    DEFAULT_MAX_EFFICIENCY_RATIO,
    backtest_pair_v2,
)

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "backtest" / "auction_mean_reversion_v2_14d"
PREREG = ROOT / "backtest" / "auction_mean_reversion_v2_preregistration.json"


def main() -> None:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    baseline = json.loads((B1_OUT_DIR / "summary.json").read_text(encoding="utf-8"))
    threshold = float(prereg["single_change"]["classification"].split("<= ")[1].split(";")[0])
    if threshold != DEFAULT_MAX_EFFICIENCY_RATIO:
        raise ValueError("Runner threshold differs from the preregistered B-v2 threshold")

    config = AuctionConfig()
    all_trades: list[dict[str, Any]] = []
    pair_metrics: dict[str, Any] = {}
    pair_audits: dict[str, Any] = {}
    data_window: dict[str, Any] = {}
    for pair in PAIRS:
        payload, rows = load_rows(DATA_DIR / f"{pair}_m5_14d.json")
        trades, audit = backtest_pair_v2(
            pair, rows, config, max_efficiency_ratio=threshold
        )
        all_trades.extend(trades)
        pair_metrics[pair] = metrics(trades)
        pair_audits[pair] = audit
        data_window[pair] = {
            "source_dataset": payload.get("source_dataset"),
            "bars": len(rows),
            "start_utc": rows[0]["time"],
            "end_utc": rows[-1]["time"],
        }

    v2_metrics = metrics(all_trades)
    b1_metrics = baseline["aggregate_metrics"]
    summary = {
        "experiment": "Strategy B-v2 — Auction / Mean-Reversion with balanced-regime filter",
        "status": "PREREGISTERED_EXPLORATORY_RESULT",
        "preregistration": "backtest/auction_mean_reversion_v2_preregistration.json",
        "single_change": prereg["single_change"],
        "baseline_reference": {
            "version": "B-v1",
            "source_commit": baseline["frozen_source_commit"],
            "metrics": b1_metrics,
        },
        "controls_held_equal_to_b1": baseline["controls"],
        "data": data_window,
        "aggregate_metrics": v2_metrics,
        "pair_metrics": pair_metrics,
        "pair_audits": pair_audits,
        "delta_vs_b1": {
            "trades": v2_metrics["trades"] - b1_metrics["trades"],
            "net_R": v2_metrics["net_R"] - b1_metrics["net_R"],
            "profit_factor": (None if v2_metrics["profit_factor"] is None or b1_metrics["profit_factor"] is None
                              else v2_metrics["profit_factor"] - b1_metrics["profit_factor"]),
        },
        "caution": "Same 14d sample used for this exploratory comparison after B-v1; no out-of-sample validation. The ER threshold was preregistered before this run but the regime hypothesis itself was motivated by B-v1 diagnostics. Costs are estimated; M5 OHLC has intrabar ambiguity.",
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(OUT_DIR / "trades.csv", all_trades)
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    rows = [
        "# Strategy B-v2 — Auction/Mean-Reversion with balanced-regime gate",
        "",
        "> Separate experiment. B-v1 remains frozen; Strategy A is unchanged.",
        "",
        "## Preregistered single change",
        "",
        "- At the completed sweep candle, compute ER(288) from M5 closes: absolute 24-hour net close displacement divided by the sum of absolute close-to-close moves.",
        "- Permit a setup only when ER <= 0.30 (BALANCED); reject the sweep when ER > 0.30 (TRENDING). No other entry, stop, target, execution, cost, or pair-universe rule changes.",
        "- All metrics use the same seven 14d cTrader datasets and estimated 1.5-pip round-turn cost as B-v1.",
        "",
        "## Aggregate comparison",
        "",
        "| Metric | B-v1 frozen | B-v2 filter | Delta |",
        "|---|---:|---:|---:|",
    ]
    for key, label in (("trades", "Trades"), ("win_rate_pct", "Win rate (%)"),
                       ("profit_factor", "Profit factor"), ("gross_R", "Gross R"),
                       ("cost_R", "Estimated cost (R)"), ("net_R", "Net R"),
                       ("average_net_R", "Average net R/trade"),
                       ("max_drawdown_R", "Max drawdown (R)")):
        a, b = b1_metrics.get(key), v2_metrics.get(key)
        delta = (None if a is None or b is None else b - a)
        fmt = lambda value: "n/a" if value is None else (str(value) if isinstance(value, int) else f"{value:.4f}")
        rows.append(f"| {label} | {fmt(a)} | {fmt(b)} | {fmt(delta)} |")
    rows += ["", "## Per-pair results", "", "| Pair | B-v1 trades | B-v2 trades | B-v2 net R | Change in net R | Trending sweeps rejected |", "|---|---:|---:|---:|---:|---:|"]
    for pair in PAIRS:
        a = baseline["pair_metrics"][pair]
        b = pair_metrics[pair]
        delta = (b["net_R"] or 0.0) - (a["net_R"] or 0.0)
        rows.append(f"| {pair} | {a['trades']} | {b['trades']} | {b['net_R']:.4f} | {delta:.4f} | {pair_audits[pair]['trending_sweeps_rejected']} |")
    rows += [
        "",
        "## Interpretation limits",
        "",
        summary["caution"],
        "",
        "This is an exploratory same-window comparison, not a proof that the filter generalizes. Aggregate R drawdown is diagnostic only; simultaneous cross-pair exposure is not modeled.",
        "",
        "Audit files: `trades.csv`, `summary.json`; rule registration: `backtest/auction_mean_reversion_v2_preregistration.json`.",
        "",
    ]
    (OUT_DIR / "report.md").write_text("\n".join(rows), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
