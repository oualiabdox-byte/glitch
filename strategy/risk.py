"""Risk management and broker-aware Forex position sizing."""
from __future__ import annotations

from datetime import datetime, timezone
from math import floor


def position_size_risk(risk_pct=0.005, account_equity=10000.0, entry_price=1.0, stop_price=0.99):
    """Legacy price-distance sizing kept only for generic research calculations."""
    risk_amount = account_equity * risk_pct
    risk_per_unit = abs(entry_price - stop_price)
    if risk_per_unit <= 0:
        return 0.0
    return risk_amount / risk_per_unit


def _attr(spec, *names, default=None):
    if isinstance(spec, dict):
        for name in names:
            if name in spec and spec[name] is not None:
                return spec[name]
    else:
        for name in names:
            value = getattr(spec, name, None)
            if value is not None:
                return value
    return default


def tick_value_per_lot_in_account(
    *,
    tick_size: float,
    lot_size: float,
    quote_to_account_rate: float,
) -> float:
    """Convert one price tick for one standard lot into account currency.

    For USD-quoted pairs in a USD account, quote_to_account_rate is 1.
    For USDJPY in a USD account it is approximately 1 / USDJPY.
    Crosses require the appropriate quote-currency/account-currency rate.
    """
    if tick_size <= 0 or lot_size <= 0 or quote_to_account_rate <= 0:
        raise ValueError("tick size, lot size and conversion rate must be positive")
    return tick_size * lot_size * quote_to_account_rate


def position_size_from_symbol(
    *,
    risk_amount: float,
    entry_price: float,
    stop_price: float,
    symbol_spec,
    tick_value_per_lot: float | None = None,
):
    """Return cTrader volume in units using symbol tick economics.

    tick_value_per_lot is the monetary value of one tick for one standard lot
    in account currency. If omitted, the function reads tickValue from the
    supplied symbol spec. Volume is clamped and rounded to the broker's step.
    """
    if risk_amount <= 0:
        raise ValueError("risk_amount must be > 0")
    distance = abs(float(entry_price) - float(stop_price))
    if distance <= 0:
        raise ValueError("entry_price and stop_price must differ")

    tick_size = float(_attr(symbol_spec, "tickSize", "tick_size", default=0.0))
    lot_size = float(_attr(symbol_spec, "lotSize", "lot_size", default=100000.0))
    conversion = float(
        _attr(symbol_spec, "quoteToAccountRate", "quote_to_account_rate", default=0.0)
    )
    if tick_value_per_lot is not None:
        tick_value = float(tick_value_per_lot)
    else:
        tick_value = float(_attr(symbol_spec, "tickValue", "tick_value", default=0.0))
        if tick_value <= 0 and conversion > 0:
            tick_value = tick_value_per_lot_in_account(
                tick_size=tick_size,
                lot_size=lot_size,
                quote_to_account_rate=conversion,
            )
    min_volume = float(_attr(symbol_spec, "minVolume", "min_volume", default=0.0))
    max_volume = float(_attr(symbol_spec, "maxVolume", "max_volume", default=float("inf")))
    step_volume = float(_attr(symbol_spec, "stepVolume", "step_volume", default=0.0))

    if tick_size <= 0 or tick_value <= 0 or lot_size <= 0:
        raise ValueError("symbol spec must provide positive tickSize, tickValue and lotSize")

    ticks_to_stop = distance / tick_size
    risk_per_lot = ticks_to_stop * tick_value
    raw_lots = risk_amount / risk_per_lot
    raw_units = raw_lots * lot_size

    if raw_units < min_volume:
        return 0.0

    units = min(raw_units, max_volume)
    if step_volume > 0:
        # Floating-point noise must not round an exact broker step down.
        units = floor(units / step_volume + 1e-9) * step_volume

    if units < min_volume:
        return 0.0
    return float(units)


def is_stop_structurally_valid(stop_price, liquidity_pool, direction):
    if direction == "LONG":
        return stop_price < liquidity_pool.get("low", float("inf"))
    return stop_price > liquidity_pool.get("high", 0)


def max_correlated_exposure(pairs_open, max_total=3):
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


def daily_loss_guard(trades, timestamp, max_daily_loss_r):
    """Return False once realized loss for the UTC day reaches the cap."""
    if max_daily_loss_r <= 0:
        return True
    day = as_utc(timestamp).date()
    realized = sum(
        float(t.get("pnl_r", 0.0))
        for t in trades
        if as_utc(t["entry_time_utc"]).date() == day
    )
    return realized > -abs(max_daily_loss_r)


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
