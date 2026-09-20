"""Displacement detection: strong momentum candles that create FVG."""


def is_displaced(candles_1h, candle_idx, min_body_atr_ratio=1.0):
    """Check if candle at candle_idx shows strong displacement.
    Uses previous 14 candles for ATR (only historical, no future data)."""
    if candle_idx < 1:
        return False
    # ATR from previous candles only (no lookahead)
    period_start = max(0, candle_idx - 14)
    prev = candles_1h[period_start:candle_idx]
    if not prev:
        return False
    # Simple ATR approximation
    highs = [c["high"] for c in prev]
    lows = [c["low"] for c in prev]
    closes = [c["close"] for c in prev]
    trs = []
    for i in range(1, len(prev)):
        h, l, pc = prev[i]["high"], prev[i]["low"], prev[i-1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = sum(trs) / len(trs) if trs else (prev[-1]["high"] - prev[-1]["low"])
    if atr <= 0:
        return False
    body = abs(candles_1h[candle_idx]["close"] - candles_1h[candle_idx]["open"])
    ratio = body / atr
    # Crypto/forex calibrated: strong displacement >= 1.0 * ATR
    return ratio >= min_body_atr_ratio
