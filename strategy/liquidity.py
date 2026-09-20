"""Liquidity detection for FX SMC/ICT backtesting.

Equal-high/equal-low tolerance is deliberately FX-calibrated. A 2% tolerance
is far too wide for major FX pairs and turns ordinary price variation into a
liquidity pool.
"""


def previous_day_high_low(candles_4h):
    if len(candles_4h) < 7:
        return None, None
    prev_day = candles_4h[-7:-1]
    return max(c["high"] for c in prev_day), min(c["low"] for c in prev_day)


def previous_week_high_low(candles_4h):
    if len(candles_4h) < 31:
        return None, None
    prev_week = candles_4h[-31:-1]
    return max(c["high"] for c in prev_week), min(c["low"] for c in prev_week)


def equal_highs_lows(candles_1h, tolerance_pct=0.0005):
    """Find approximate equal highs/lows using a 0.05% FX tolerance."""
    highs = [c["high"] for c in candles_1h]
    lows = [c["low"] for c in candles_1h]
    eqh, eql = [], []

    for i in range(len(highs) - 1):
        for j in range(i + 1, len(highs)):
            diff_pct = abs(highs[i] - highs[j]) / max(abs(highs[i]), abs(highs[j]), 1e-12)
            if diff_pct <= tolerance_pct:
                eqh.append({"price": (highs[i] + highs[j]) / 2.0, "count": 2})

    for i in range(len(lows) - 1):
        for j in range(i + 1, len(lows)):
            diff_pct = abs(lows[i] - lows[j]) / max(abs(lows[i]), abs(lows[j]), 1e-12)
            if diff_pct <= tolerance_pct:
                eql.append({"price": (lows[i] + lows[j]) / 2.0, "count": 2})

    return eqh, eql


def liquidity_pools(candles_4h):
    pools = []
    pdh, pdl = previous_day_high_low(candles_4h)
    pwh, pwl = previous_week_high_low(candles_4h)

    if pdh is not None:
        pools.append({"type": "resistance", "price": pdh, "source": "PDH", "strength": "medium"})
    if pdl is not None:
        pools.append({"type": "support", "price": pdl, "source": "PDL", "strength": "medium"})
    if pwh is not None:
        pools.append({"type": "resistance", "price": pwh, "source": "PWH", "strength": "high"})
    if pwl is not None:
        pools.append({"type": "support", "price": pwl, "source": "PWL", "strength": "high"})

    eqh, eql = equal_highs_lows(candles_4h[-20:])
    for e in eqh:
        pools.append({"type": "resistance", "price": e["price"], "source": "EQH", "strength": "low"})
    for e in eql:
        pools.append({"type": "support", "price": e["price"], "source": "EQL", "strength": "low"})
    return pools
