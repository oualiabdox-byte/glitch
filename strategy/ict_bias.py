"""Higher-timeframe directional context using confirmed 4H swing structure."""


def htf_bias_4h(candles_4h):
    """Return LONG/SHORT only when the last confirmed swings agree.

    Swing confirmation uses candles on both sides of the swing, so the current
    candle is never treated as a confirmed future swing. Mixed structure returns
    None rather than inventing a directional bias.
    """
    if len(candles_4h) < 12:
        return None

    # Local import avoids coupling the strategy modules at import time.
    from .market_structure import find_swing_highs, find_swing_lows

    highs = find_swing_highs(candles_4h, length=2)
    lows = find_swing_lows(candles_4h, length=2)
    if len(highs) >= 2 and len(lows) >= 2:
        h1, h2 = highs[-2], highs[-1]
        l1, l2 = lows[-2], lows[-1]
        if h2["high"] > h1["high"] and l2["low"] > l1["low"]:
            return "LONG"
        if h2["high"] < h1["high"] and l2["low"] < l1["low"]:
            return "SHORT"

    # Conservative fallback: only use a range break relative to an older
    # closed block. This avoids forcing a bias in mixed/choppy structure.
    if len(candles_4h) >= 24:
        recent = candles_4h[-8:]
        older = candles_4h[-24:-8]
        recent_high = max(c["high"] for c in recent)
        recent_low = min(c["low"] for c in recent)
        older_high = max(c["high"] for c in older)
        older_low = min(c["low"] for c in older)
        if recent_high > older_high and recent_low >= older_low:
            return "LONG"
        if recent_low < older_low and recent_high <= older_high:
            return "SHORT"

    return None


def daily_bias_4h(candles_4h):
    return htf_bias_4h(candles_4h)
