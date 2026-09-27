"""Conservative broker-aware position sizing for demo execution.

The strategy decides whether a setup exists. This module only converts an
already-approved signal into a broker-valid volume. Risk mode is opt-in.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Mapping, Any


@dataclass(frozen=True)
class VolumeDecision:
    volume_units: float
    mode: str
    requested_volume_units: float
    risk_cash: float | None = None
    estimated_loss_cash: float | None = None


def _positive(name: str, value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be > 0")
    return number


def _floor_to_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    return math.floor((value / step) + 1e-9) * step


def normalize_volume(volume_units: float, symbol_spec: Mapping[str, Any], max_volume_units: float = 0.0) -> float:
    """Return a broker-valid volume without ever rounding risk upward."""
    requested = _positive("volume_units", volume_units)
    minimum = float(symbol_spec.get("minVolume") or 0)
    maximum = float(symbol_spec.get("maxVolume") or 0)
    step = float(symbol_spec.get("stepVolume") or 0)
    if minimum < 0 or maximum < 0 or step < 0:
        raise ValueError("symbol volume limits cannot be negative")
    upper = requested
    if maximum > 0:
        upper = min(upper, maximum)
    if max_volume_units > 0:
        upper = min(upper, max_volume_units)
    normalized = _floor_to_step(upper, step)
    if minimum > 0 and normalized < minimum:
        raise ValueError(f"volume {requested} is below the broker minimum after safe rounding (minimum={minimum}, step={step})")
    if normalized <= 0:
        raise ValueError("volume rounds to zero")
    return float(normalized)


def calculate_risk_volume(account_equity: float, risk_per_trade_pct: float, stop_distance_price: float, cash_per_unit_price_move: float, symbol_spec: Mapping[str, Any], max_volume_units: float = 0.0) -> VolumeDecision:
    """Size from equity and stop distance using an explicit cash conversion."""
    equity = _positive("account_equity", account_equity)
    risk_pct = _positive("risk_per_trade_pct", risk_per_trade_pct)
    if risk_pct > 1:
        raise ValueError("risk_per_trade_pct must be <= 1")
    stop_distance = _positive("stop_distance_price", stop_distance_price)
    cash_per_move = _positive("cash_per_unit_price_move", cash_per_unit_price_move)
    risk_cash = equity * risk_pct
    requested = risk_cash / (stop_distance * cash_per_move)
    volume = normalize_volume(requested, symbol_spec, max_volume_units)
    return VolumeDecision(volume, "risk", requested, risk_cash, volume * stop_distance * cash_per_move)


def resolve_order_volume(signal: Mapping[str, Any], symbol_spec: Mapping[str, Any], environ: Mapping[str, str] | None = None, risk_defaults: Mapping[str, Any] | None = None) -> VolumeDecision:
    """Resolve fixed or opt-in risk sizing from explicit environment inputs."""
    env = os.environ if environ is None else environ
    defaults = risk_defaults or {}
    mode = env.get("CTRADER_SIZING_MODE", "fixed").strip().lower()
    max_volume = _positive("CTRADER_MAX_ORDER_VOLUME_UNITS", env.get("CTRADER_MAX_ORDER_VOLUME_UNITS"))
    if mode == "fixed":
        requested = _positive("CTRADER_ORDER_VOLUME_UNITS", env.get("CTRADER_ORDER_VOLUME_UNITS"))
        return VolumeDecision(normalize_volume(requested, symbol_spec, max_volume), mode, requested)
    if mode != "risk":
        raise ValueError("CTRADER_SIZING_MODE must be fixed or risk")
    if "CTRADER_ACCOUNT_EQUITY" not in env or "CTRADER_CASH_PER_UNIT_PRICE_MOVE" not in env:
        raise ValueError("risk sizing requires CTRADER_ACCOUNT_EQUITY and CTRADER_CASH_PER_UNIT_PRICE_MOVE")
    risk_pct = env.get("CTRADER_RISK_PER_TRADE_PCT", str(defaults.get("risk_per_trade_pct", 0.005)))
    entry = _positive("signal.entry_price", signal.get("entry_price"))
    stop = _positive("signal.stop_price", signal.get("stop_price"))
    return calculate_risk_volume(equity=env["CTRADER_ACCOUNT_EQUITY"], risk_per_trade_pct=risk_pct, stop_distance_price=abs(entry - stop), cash_per_unit_price_move=env["CTRADER_CASH_PER_UNIT_PRICE_MOVE"], symbol_spec=symbol_spec, max_volume_units=max_volume)
