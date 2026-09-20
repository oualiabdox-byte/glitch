"""Market structure: HTF structure, MSS/CHoCH detection, no repaint."""


def is_higher_timeframe_uptrend(candles_4h):
    """Check if last 20 4H candles show HH/HL structure — deterministic after close."""
    if len(candles_4h) < 10:
        return None
    recent = candles_4h[-12:]  # last 3 days of 4H
    # Simple: last high > previous high, last low > previous low
    highs = [c["high"] for c in recent]
    lows = [c["low"] for c in recent]
    # Higher high if last high > max of previous 11
    last_high = highs[-1]
    prev_highs = highs[:-1]
    # Higher low if last low > min of previous 11
    last_low = lows[-1]
    prev_lows = lows[:-1]
    if last_high > max(prev_highs) and last_low > min(prev_lows):
        return "uptrend"
    if last_high < min(prev_highs) and last_low < max(prev_lows):
        return "downtrend"
    return None


def find_swing_highs(candles, length=5):
    """Find peak highs — only confirmed after enough candles have passed."""
    out = []
    for i in range(length, len(candles) - length):
        c = candles[i]
        if all(c["high"] >= candles[i - j]["high"] for j in range(1, length + 1)) and \
           all(c["high"] > candles[i + j]["high"] for j in range(1, length + 1)):
            out.append({"time": c["time"], "high": c["high"], "idx": i})
    return out


def find_swing_lows(candles, length=5):
    out = []
    for i in range(length, len(candles) - length):
        c = candles[i]
        if all(c["low"] <= candles[i - j]["low"] for j in range(1, length + 1)) and \
           all(c["low"] < candles[i + j]["low"] for j in range(1, length + 1)):
            out.append({"time": c["time"], "low": c["low"], "idx": i})
    return out


def mss_confirmed(candles_1h, direction, reference_time):
    """Market Structure Shift: close breaks opposing swing after reference_time."""
    pre = [c for c in candles_1h if c["time"] <= reference_time]
    post = [c for c in candles_1h if c["time"] > reference_time]
    if not pre or not post:
        return False, None
    if direction == "LONG":
        # Find recent swing low in pre, check if post closes above it
        lows = find_swing_lows(pre)
        if not lows:
            return False, None
        ref = lows[-1]["low"]
        broken = any(c["close"] > ref for c in post)
        return broken, ref
    else:
        highs = find_swing_highs(pre)
        if not highs:
            return False, None
        ref = highs[-1]["high"]
        broken = any(c["close"] < ref for c in post)
        return broken, ref
