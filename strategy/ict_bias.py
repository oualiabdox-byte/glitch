"""ICT Bias: HTF structure + session context."""


def htf_bias_4h(candles_4h):
    """Determine HTF directional bias from 4H structure.
    Uses only closed candles (no repaint)."""
    if len(candles_4h) < 12:
        return None
    # Compare recent structure vs older reference
    last = candles_4h[-1]
    ref_6 = candles_4h[-7]  # ~1.5 days back
    ref_12 = candles_4h[-13]  # ~3 days back

    # Simple trend detection: higher highs and higher lows over 3-day window
    recent_high = max(c["high"] for c in candles_4h[-12:])
    older_high = max(c["high"] for c in candles_4h[-24:-12]) if len(candles_4h) >= 24 else max(c["high"] for c in candles_4h[:6])
    recent_low = min(c["low"] for c in candles_4h[-12:])
    older_low = min(c["low"] for c in candles_4h[-24:-12]) if len(candles_4h) >= 24 else min(c["low"] for c in candles_4h[:6])

    if recent_high > older_high and recent_low > older_low:
        return "LONG"
    if recent_high < older_high and recent_low < older_low:
        return "SHORT"
    # Mixed: check if recent close > recent open (momentum)
    if last["close"] > last["open"] and recent_high > older_high:
        return "LONG"
    if last["close"] < last["open"] and recent_low < older_low:
        return "SHORT"
    return None


def daily_bias_4h(candles_4h):
    """Daily session bias from 4H structure — simpler version."""
    return htf_bias_4h(candles_4h)
