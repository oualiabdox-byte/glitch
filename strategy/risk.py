"""Risk management: fixed fractional, position sizing, correlation limits."""


def position_size_risk(risk_pct=0.005, account_equity=10000.0, entry_price=1.0, stop_price=0.99):
    """Calculate units based on fixed fractional risk.
    Uses 0.5% default per user spec."""
    risk_amount = account_equity * risk_pct
    risk_per_unit = abs(entry_price - stop_price)
    if risk_per_unit <= 0:
        return 0.0
    units = risk_amount / risk_per_unit
    return units


def max_correlated_exposure(pairs_open, max_total=3):
    """Limit USD-pair correlated exposure (e.g., EURUSD and GBPUSD both USD-quoted)."""
    # For simplicity: cap total open positions across USD-pairs
    return len(pairs_open) < max_total


def is_stop_structurally_valid(stop_price, liquidity_pool, direction):
    """Stop must be beyond the invalidation/swept extreme (not arbitrary)."""
    if direction == "LONG":
        return stop_price < liquidity_pool.get("low", float('inf'))
    else:
        return stop_price > liquidity_pool.get("high", 0)
