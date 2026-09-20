"""Liquidity detection: DOL, PDH/PDL, PWH/PWL, EQH/EQL, liquidity pools."""


def previous_day_high_low(candles_4h):
    """Get previous day (last 6 candles ~ 24h) high/low from 4H data."""
    if len(candles_4h) < 6:
        return None, None
    prev_day = candles_4h[-7:-1]  # previous 6 candles before current
    return max(c["high"] for c in prev_day), min(c["low"] for c in prev_day)


def previous_week_high_low(candles_4h):
    """Previous week from 4H: ~30 candles = 5 trading days."""
    if len(candles_4h) < 30:
        return None, None
    prev_week = candles_4h[-31:-1]
    return max(c["high"] for c in prev_week), min(c["low"] for c in prev_week)


def equal_highs_lows(candles_1h, tolerance_pct=0.02):
    """Find equal highs (resistance pool) and equal lows (support pool)."""
    highs = [c["high"] for c in candles_1h]
    lows = [c["low"] for c in candles_1h]
    eqh = []
    eql = []
    # Find highs that are within tolerance of each other (pool formation)
    for i in range(len(highs) - 1):
        for j in range(i + 1, len(highs)):
            diff_pct = abs(highs[i] - highs[j]) / max(highs[i], highs[j])
            if diff_pct <= tolerance_pct:
                eqh.append({"price": (highs[i] + highs[j]) / 2, "count": 2})
    for i in range(len(lows) - 1):
        for j in range(i + 1, len(lows)):
            diff_pct = abs(lows[i] - lows[j]) / max(lows[i], lows[j])
            if diff_pct <= tolerance_pct:
                eql.append({"price": (lows[i] + lows[j]) / 2, "count": 2})
    return eqh, eql


def liquidity_pools(candles_4h):
    """Identify draw-on-liquidity targets and liquidity pools."""
    pools = []
    # Previous day high = resistance / BSL target
    # Previous day low = support / SSL target
    # Previous week = larger targets
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
    # Equal highs / lows from recent 4H
    eqh, eql = equal_highs_lows(candles_4h[-20:])
    for e in eqh:
        pools.append({"type": "resistance", "price": e["price"], "source": "EQH", "strength": "low"})
    for e in eql:
        pools.append({"type": "support", "price": e["price"], "source": "EQL", "strength": "low"})
    return pools
