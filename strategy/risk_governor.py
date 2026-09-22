"""Fail-closed, broker-aware pre-trade risk gate."""
from __future__ import annotations

from datetime import datetime, timezone

from . import risk


def _utc(value):
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _pip_size(symbol):
    return 0.01 if "JPY" in symbol.upper() else 0.0001


def evaluate_risk(candidate, account, open_positions, realized_trades, symbol_spec, quote, limits):
    """Return an auditable APPROVED/REJECTED decision; never raises for bad input."""
    reasons = []
    try:
        symbol = str(candidate["symbol"]).upper()
        side = str(candidate["side"]).upper()
        entry = float(candidate["entry_price"])
        stop = float(candidate["stop_price"])
        equity = float(account["equity"])
        now = _utc(quote["timestamp"])
        quote_time = _utc(quote["timestamp"])
        bid = float(quote["bid"])
        ask = float(quote["ask"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return {"status": "REJECTED", "reason_codes": ["INVALID_INPUT"], "units": 0.0}

    if equity <= 0:
        reasons.append("INVALID_EQUITY")
    if side not in {"LONG", "SHORT"}:
        reasons.append("INVALID_SIDE")
    if (side == "LONG" and stop >= entry) or (side == "SHORT" and stop <= entry):
        reasons.append("INVALID_STOP_DIRECTION")
    if bid <= 0 or ask <= 0 or ask < bid:
        reasons.append("INVALID_QUOTE")
    if limits.get("max_quote_age_seconds", 0) > 0:
        age = abs((_utc(account.get("as_of", now)) - quote_time).total_seconds())
        if age > float(limits["max_quote_age_seconds"]):
            reasons.append("STALE_QUOTE")
    spread_pips = (ask - bid) / _pip_size(symbol) if ask >= bid else float("inf")
    if spread_pips > float(limits.get("max_spread_pips", float("inf"))):
        reasons.append("SPREAD_LIMIT")
    if len(open_positions) >= int(limits.get("max_open_positions", 10**9)):
        reasons.append("MAX_OPEN_POSITIONS")
    if float(account.get("drawdown_r", 0.0)) >= float(limits.get("max_drawdown_r", float("inf"))):
        reasons.append("MAX_DRAWDOWN")

    risk_amount = float(candidate.get("risk_amount", equity * float(limits.get("risk_pct", 0.005))))
    if risk_amount <= 0:
        reasons.append("INVALID_RISK_AMOUNT")
    if reasons:
        return {"status": "REJECTED", "reason_codes": reasons, "units": 0.0, "spread_pips": spread_pips}

    try:
        units = risk.position_size_from_symbol(
            risk_amount=risk_amount,
            entry_price=entry,
            stop_price=stop,
            symbol_spec=symbol_spec,
        )
    except (TypeError, ValueError):
        units = 0.0
    if units <= 0:
        reasons.append("REJECT_VOLUME")

    day = now.date()
    realized_loss_r = sum(
        min(0.0, float(t.get("pnl_r", 0.0)))
        for t in realized_trades
        if _utc(t.get("entry_time_utc", now)).date() == day
    )
    open_risk_r = sum(
        max(0.0, float(p.get("worst_case_r", p.get("worst_case_risk_r", 0.0))))
        for p in open_positions
    )
    candidate_r = risk_amount / equity
    max_daily = float(limits.get("max_daily_loss_r", float("inf")))
    if -realized_loss_r + open_risk_r + candidate_r > max_daily:
        reasons.append("DAILY_LOSS_AND_OPEN_RISK_LIMIT")
    if candidate_r > float(limits.get("max_risk_per_trade_r", float("inf"))):
        reasons.append("RISK_PER_TRADE_LIMIT")
    if units > float(limits.get("max_volume", float("inf"))):
        reasons.append("MAX_VOLUME")
    return {
        "status": "APPROVED" if not reasons else "REJECTED",
        "reason_codes": reasons,
        "units": float(units) if not reasons else 0.0,
        "risk_amount": risk_amount,
        "risk_r": candidate_r,
        "spread_pips": spread_pips,
    }
