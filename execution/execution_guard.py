"""Pure Demo execution safety checks.

This module contains no broker calls. It evaluates whether a signal remains
tradable at the executable quote and computes the protection distances that
must be sent to cTrader before the fill, followed by absolute post-fill
reconciliation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class ExecutionCheck:
    approved: bool
    reason_codes: tuple[str, ...]
    expected_fill: float | None
    spread_price: float | None
    spread_pips: float | None
    price_drift_pips: float | None
    execution_rr: float | None
    stop_distance: float | None
    target_distance: float | None


def _pip_size(pair: str) -> float:
    pair = pair.upper().replace("/", "")
    return 0.01 if "JPY" in pair else 0.0001


def _age_seconds(timestamp: str, now: datetime) -> float:
    ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (now - ts.astimezone(timezone.utc)).total_seconds()


def evaluate_execution(
    signal: dict[str, Any],
    *,
    bid: float,
    ask: float,
    now: datetime | None = None,
    max_signal_age_seconds: float = 300.0,
    max_spread_pips: float = 3.0,
    max_price_drift_pips: float = 2.0,
    min_execution_rr: float = 0.0,
) -> ExecutionCheck:
    now = now or datetime.now(timezone.utc)
    pair = str(signal["pair"]).upper()
    side = str(signal["side"]).upper()
    entry = float(signal["entry_price"])
    stop = float(signal["stop_price"])
    target = float(signal.get("target_price", signal.get("tp_target")))
    bid = float(bid)
    ask = float(ask)

    pip = _pip_size(pair)
    expected_fill = ask if side in {"LONG", "BUY"} else bid
    spread_price = ask - bid
    spread_pips = spread_price / pip
    drift_pips = abs(expected_fill - entry) / pip

    stop_distance = abs(expected_fill - stop)
    target_distance = abs(target - expected_fill)
    execution_rr = target_distance / stop_distance if stop_distance > 0 else None

    reasons: list[str] = []
    if bid <= 0 or ask <= 0 or ask < bid:
        reasons.append("INVALID_QUOTE")
    if spread_pips > max_spread_pips:
        reasons.append("SPREAD_TOO_WIDE")
    if drift_pips > max_price_drift_pips:
        reasons.append("PRICE_DRIFT_TOO_LARGE")
    if "timestamp" in signal:
        age = _age_seconds(str(signal["timestamp"]), now)
        if age < 0:
            reasons.append("SIGNAL_FROM_FUTURE")
        elif age > max_signal_age_seconds:
            reasons.append("SIGNAL_TOO_OLD")
    if stop_distance <= 0:
        reasons.append("INVALID_STOP_AT_EXECUTION")
    if target_distance <= 0:
        reasons.append("TARGET_INVALIDATED_AT_EXECUTION")
    if execution_rr is not None and execution_rr < min_execution_rr:
        reasons.append("EXECUTION_RR_TOO_LOW")

    return ExecutionCheck(
        approved=not reasons,
        reason_codes=tuple(reasons),
        expected_fill=expected_fill,
        spread_price=spread_price,
        spread_pips=spread_pips,
        price_drift_pips=drift_pips,
        execution_rr=execution_rr,
        stop_distance=stop_distance,
        target_distance=target_distance,
    )
