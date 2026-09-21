"""Risk management: position sizing, structure validity and execution gates."""
from __future__ import annotations

from datetime import datetime, timezone


def position_size_risk(risk_pct=0.005, account_equity=10000.0, entry_price=1.0, stop_price=0.99):
    """Calculate units based on fixed-fractional account risk."""
    risk_amount = account_equity * risk_pct
    risk_per_unit = abs(entry_price - stop_price)
    if risk_per_unit <= 0:
        return 0.0
    return risk_amount / risk_per_unit


def is_stop_structurally_valid(stop_price, liquidity_pool, direction):
    """Stop must be beyond the structural invalidation/swept extreme."""
    if direction == "LONG":
        return stop_price < liquidity_pool.get("low", float("inf"))
    return stop_price > liquidity_pool.get("high", 0)


def max_correlated_exposure(pairs_open, max_total=3):
    """Cap total simultaneously open positions."""
    return len(pairs_open) < max_total


def as_utc(value):
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def trades_on_day(trades, timestamp):
    day = as_utc(timestamp).date()
    return sum(1 for t in trades if as_utc(t["entry_time_utc"]).date() == day)


def cooldown_clear(last_entry_time, current_time, cooldown_minutes):
    if last_entry_time is None or cooldown_minutes <= 0:
        return True
    elapsed = (as_utc(current_time) - as_utc(last_entry_time)).total_seconds() / 60.0
    return elapsed >= cooldown_minutes


def drawdown_guard(equity_r, peak_r, max_drawdown_r):
    if max_drawdown_r <= 0:
        return True
    return (peak_r - equity_r) < max_drawdown_r


def pair_currencies(pair):
    clean = "".join(ch for ch in pair.upper() if ch.isalpha())
    if len(clean) != 6:
        return ()
    return clean[:3], clean[3:]


def currency_exposure_allowed(open_pairs, candidate_pair, max_shared_currency=2):
    if max_shared_currency <= 0:
        return True
    proposed = list(open_pairs) + [candidate_pair]
    counts = {}
    for pair in proposed:
        for currency in pair_currencies(pair):
            counts[currency] = counts.get(currency, 0) + 1
    return max(counts.values(), default=0) <= max_shared_currency
