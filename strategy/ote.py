"""OTE zone utilities — Fibonacci 0.618/0.705/0.786 retracement.

This module only describes a retracement zone. It never creates a trade by
itself, so it can be used as optional confluence without starving the model.
"""

def compute_ote(impulse_low, impulse_high, side):
    if impulse_high <= impulse_low:
        return None
    rng = impulse_high - impulse_low
    if side == "LONG":
        return {
            "side": side,
            "top": impulse_high - rng * 0.618,
            "bottom": impulse_high - rng * 0.786,
            "mid": impulse_high - rng * 0.705,
        }
    if side == "SHORT":
        return {
            "side": side,
            "bottom": impulse_low + rng * 0.618,
            "top": impulse_low + rng * 0.786,
            "mid": impulse_low + rng * 0.705,
        }
    return None

def price_in_ote(price, zone):
    return bool(zone and zone["bottom"] <= price <= zone["top"])
