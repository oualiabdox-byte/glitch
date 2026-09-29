"""Strategy B-v2: frozen B-v1 rules plus one preregistered regime gate.

Only setups whose completed sweep-bar 24h M5 close-path efficiency ratio is at
or below the registered threshold are allowed to proceed. Entry, stop, target,
cost, confirmation, and execution logic are copied unchanged from B-v1.
"""
from __future__ import annotations

from typing import Any

from .auction_mean_reversion import (
    AuctionConfig,
    Side,
    atr_at,
    confirms_reversal,
    detect_sweep,
    resolve_exit,
)

DEFAULT_MAX_EFFICIENCY_RATIO = 0.30


def efficiency_ratio(
    rows: list[dict[str, Any]], end_index: int, lookback: int = 288
) -> float:
    """Kaufman-style path ER using only closes through ``end_index``.

    ER is net close-to-close displacement divided by total absolute close path;
    it is bounded in [0, 1]. A zero path is classified as balanced (ER=0).
    """
    if lookback < 1 or end_index < lookback or end_index >= len(rows):
        raise ValueError("ER needs a valid endpoint with at least lookback prior intervals")
    net = abs(float(rows[end_index]["close"]) - float(rows[end_index - lookback]["close"]))
    path = sum(
        abs(float(rows[index]["close"]) - float(rows[index - 1]["close"]))
        for index in range(end_index - lookback + 1, end_index + 1)
    )
    return net / path if path else 0.0


def backtest_pair_v2(
    pair: str,
    rows: list[dict[str, Any]],
    config: AuctionConfig = AuctionConfig(),
    max_efficiency_ratio: float | None = DEFAULT_MAX_EFFICIENCY_RATIO,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Return B-v2 trades and gate diagnostics for one FX pair.

    A value of ``None`` disables only the ER gate and is used to regression-test
    that all other mechanics exactly reproduce the frozen B-v1 backtest.
    """
    if max_efficiency_ratio is not None and not 0.0 <= max_efficiency_ratio <= 1.0:
        raise ValueError("max_efficiency_ratio must be between 0 and 1, or None")
    pip_size = 0.01 if pair.upper().endswith("JPY") else 0.0001
    min_history = max(config.range_lookback_bars, config.liquidity_lookback_bars)
    trades: list[dict[str, Any]] = []
    audit = {
        "sweep_candidates": 0,
        "balanced_sweeps_allowed": 0,
        "trending_sweeps_rejected": 0,
        "confirmed_entries": 0,
    }
    index = min_history

    while index + 1 < len(rows):
        current = rows[index]
        context = rows[index - config.range_lookback_bars:index]
        prior_liquidity = rows[index - config.liquidity_lookback_bars:index]
        range_low = min(float(row["low"]) for row in context)
        range_high = max(float(row["high"]) for row in context)
        pending = detect_sweep(current, prior_liquidity, range_low, range_high, config)
        if pending is None:
            index += 1
            continue

        audit["sweep_candidates"] += 1
        er = efficiency_ratio(rows, index, config.range_lookback_bars)
        if max_efficiency_ratio is not None and er > max_efficiency_ratio:
            audit["trending_sweeps_rejected"] += 1
            index += 1
            continue
        audit["balanced_sweeps_allowed"] += 1

        sweep_index = index
        sweep_atr = atr_at(rows, sweep_index, config.atr_period)
        buffer = max(config.stop_atr_buffer * sweep_atr,
                     config.min_stop_buffer_pips * pip_size)
        confirmed_index: int | None = None
        last_confirmation = min(len(rows) - 2, sweep_index + config.pending_expiry_bars)
        for candidate_index in range(sweep_index + 1, last_confirmation + 1):
            candidate = rows[candidate_index]
            if pending["side"] == "LONG":
                if float(candidate["low"]) <= float(pending["sweep_extreme"]):
                    break
            elif float(candidate["high"]) >= float(pending["sweep_extreme"]):
                break
            pivot_start = max(sweep_index, candidate_index - config.choch_lookback_bars)
            pivots = rows[pivot_start:candidate_index]
            if len(pivots) == config.choch_lookback_bars and confirms_reversal(
                pending["side"], candidate, pivots
            ):
                confirmed_index = candidate_index
                break

        if confirmed_index is None:
            index += 1
            continue

        entry_index = confirmed_index + 1
        entry = float(rows[entry_index]["open"])
        side: Side = pending["side"]
        stop = (float(pending["sweep_extreme"]) - buffer if side == "LONG"
                else float(pending["sweep_extreme"]) + buffer)
        target = float(pending["value_midpoint"])
        risk = entry - stop if side == "LONG" else stop - entry
        reward = target - entry if side == "LONG" else entry - target
        planned_rr = reward / risk if risk > 0 else 0.0
        if risk <= 0 or reward <= 0 or planned_rr < config.min_reward_risk:
            index = confirmed_index + 1
            continue

        exit_index = min(len(rows) - 1, entry_index + config.max_holding_bars - 1)
        exit_price, exit_reason = float(rows[exit_index]["close"]), "end_of_data"
        for bar_index in range(entry_index, exit_index + 1):
            hit = resolve_exit(side, rows[bar_index], stop, target)
            if hit is not None:
                exit_price, exit_reason = hit
                exit_index = bar_index
                break
            if bar_index == entry_index + config.max_holding_bars - 1:
                exit_price, exit_reason = float(rows[bar_index]["close"]), "time_exit"

        signed_move = exit_price - entry if side == "LONG" else entry - exit_price
        gross_r = signed_move / risk
        cost_r = config.round_turn_cost_pips * pip_size / risk
        trade = {
            "pair": pair.upper(),
            "strategy": "auction_mean_reversion_b",
            "side": side,
            "sweep_time_utc": str(rows[sweep_index]["time"]),
            "signal_time_utc": str(rows[confirmed_index]["time"]),
            "entry_time_utc": str(rows[entry_index]["time"]),
            "exit_time_utc": str(rows[exit_index]["time"]),
            "entry_price": entry,
            "stop_price": stop,
            "target_price": target,
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "risk_distance": risk,
            "planned_rr": planned_rr,
            "gross_R": gross_r,
            "cost_R": cost_r,
            "net_R": gross_r - cost_r,
            "range_low_at_sweep": float(pending["range_low"]),
            "range_high_at_sweep": float(pending["range_high"]),
        }
        if max_efficiency_ratio is not None:
            trade["sweep_efficiency_ratio"] = er
            trade["regime_state"] = "BALANCED"
        trades.append(trade)
        audit["confirmed_entries"] += 1
        index = exit_index + 1

    return trades, audit
