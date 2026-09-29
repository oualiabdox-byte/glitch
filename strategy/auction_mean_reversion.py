"""Standalone Auction/Mean-Reversion Strategy B for research backtests.

This deliberately does not call the canonical ICT/SMC POI strategy. Its signal
sequence is a rolling auction-range extreme, a close-back-inside sweep of recent
M5 liquidity, then a directional M5 rejection/three-bar break. It is signal-only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Side = Literal["LONG", "SHORT"]


@dataclass(frozen=True)
class AuctionConfig:
    value_fraction: float = 0.15
    range_lookback_bars: int = 288       # 24 hours of M5 bars
    liquidity_lookback_bars: int = 12    # prior hour of M5 bars
    choch_lookback_bars: int = 3
    pending_expiry_bars: int = 6
    atr_period: int = 14
    stop_atr_buffer: float = 0.10
    min_stop_buffer_pips: float = 0.5
    min_reward_risk: float = 1.0
    max_holding_bars: int = 288          # 24 hours
    round_turn_cost_pips: float = 1.5


def _true_range(row: dict[str, Any], previous_close: float | None) -> float:
    high, low = float(row["high"]), float(row["low"])
    if previous_close is None:
        return high - low
    return max(high - low, abs(high - previous_close), abs(low - previous_close))


def atr_at(rows: list[dict[str, Any]], end_index: int, period: int = 14) -> float:
    """Simple mean true range ending at a fully closed bar."""
    start = max(0, end_index - period + 1)
    values = []
    for index in range(start, end_index + 1):
        previous_close = float(rows[index - 1]["close"]) if index else None
        values.append(_true_range(rows[index], previous_close))
    return sum(values) / len(values) if values else 0.0


def detect_sweep(
    current: dict[str, Any],
    prior_liquidity_bars: list[dict[str, Any]],
    range_low: float,
    range_high: float,
    config: AuctionConfig = AuctionConfig(),
) -> dict[str, Any] | None:
    """Return an extreme/value sweep, using only closed bars before current."""
    if not prior_liquidity_bars or range_high <= range_low:
        return None
    span = range_high - range_low
    open_, close = float(current["open"]), float(current["close"])
    high, low = float(current["high"]), float(current["low"])
    bar_span = high - low
    if bar_span <= 0:
        return None

    prior_low = min(float(row["low"]) for row in prior_liquidity_bars)
    prior_high = max(float(row["high"]) for row in prior_liquidity_bars)
    lower_edge = range_low + config.value_fraction * span
    upper_edge = range_high - config.value_fraction * span

    long_sweep = (
        low < prior_low and close > prior_low and close <= lower_edge
        and close > open_ and close >= low + 0.60 * bar_span
    )
    short_sweep = (
        high > prior_high and close < prior_high and close >= upper_edge
        and close < open_ and close <= low + 0.40 * bar_span
    )
    if long_sweep == short_sweep:  # neither, or an ambiguous two-sided bar
        return None
    side: Side = "LONG" if long_sweep else "SHORT"
    return {
        "side": side,
        "liquidity_level": prior_low if side == "LONG" else prior_high,
        "sweep_extreme": low if side == "LONG" else high,
        "range_low": range_low,
        "range_high": range_high,
        "value_midpoint": (range_low + range_high) / 2.0,
        "sweep_close": close,
    }


def confirms_reversal(
    side: Side,
    current: dict[str, Any],
    prior_bars: list[dict[str, Any]],
) -> bool:
    """Confirm rejection plus a close beyond the preceding local three-bar pivot."""
    if not prior_bars:
        return False
    open_, close = float(current["open"]), float(current["close"])
    high, low = float(current["high"]), float(current["low"])
    span = high - low
    if span <= 0:
        return False
    if side == "LONG":
        pivot = max(float(row["high"]) for row in prior_bars)
        return close > open_ and close > pivot and close >= low + 0.65 * span
    pivot = min(float(row["low"]) for row in prior_bars)
    return close < open_ and close < pivot and close <= low + 0.35 * span


def resolve_exit(
    side: Side,
    bar: dict[str, Any],
    stop: float,
    target: float,
) -> tuple[float, str] | None:
    """Conservative OHLC fill: gap-aware and stop-first if both levels trade."""
    open_, high, low = float(bar["open"]), float(bar["high"]), float(bar["low"])
    if side == "LONG":
        if open_ <= stop:
            return open_, "stop_gap"
        if open_ >= target:
            return target, "target_gap"
        if low <= stop:
            return stop, "stop"
        if high >= target:
            return target, "target"
    else:
        if open_ >= stop:
            return open_, "stop_gap"
        if open_ <= target:
            return target, "target_gap"
        if high >= stop:
            return stop, "stop"
        if low <= target:
            return target, "target"
    return None


def backtest_pair(
    pair: str,
    rows: list[dict[str, Any]],
    config: AuctionConfig = AuctionConfig(),
) -> list[dict[str, Any]]:
    """Generate and execute separate per-pair Strategy B trades on M5 OHLC.

    Signals use only completed bars. Entries are the next bar's open; the rolling
    24-hour high/low and value midpoint are frozen at the sweep bar. One position
    per pair is allowed at a time. No live/demo order path is called.
    """
    pip_size = 0.01 if pair.upper().endswith("JPY") else 0.0001
    min_history = max(config.range_lookback_bars, config.liquidity_lookback_bars)
    trades: list[dict[str, Any]] = []
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
        trades.append({
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
        })
        index = exit_index + 1

    return trades
