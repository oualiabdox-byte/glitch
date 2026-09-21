"""Dominating Candle (DC) detector translated from TrendDayTrader's MQL5 logic.

The source defines a historical candle whose FULL high/low range contains
the BODY (open/close) of at least N newer closed candles. The DC remains
valid until a newer CLOSED candle closes outside its range.

This module is causal: it only uses candles at or before the supplied
closed-bar timestamp. It does not generate entries by itself; callers can
use the DC as structural confluence or as an explicit experimental trigger.
"""


def find_dominating_candle(candles, min_contained=3, lookback=8):
    """Return the most recent qualifying DC, or None.

    candles must be chronological (oldest -> newest) and contain closed
    candles only. The returned DC is the candidate whose full range contains
    every newer candle body up to the current bar.
    """
    if len(candles) < min_contained + 1 or min_contained < 3:
        return None

    newest = len(candles) - 1
    start = max(0, newest - lookback)

    for idx in range(newest - min_contained, start - 1, -1):
        dc = candles[idx]
        low = float(dc["low"])
        high = float(dc["high"])

        contained = True
        for j in range(idx + 1, newest + 1):
            body_low = min(float(candles[j]["open"]), float(candles[j]["close"]))
            body_high = max(float(candles[j]["open"]), float(candles[j]["close"]))
            if body_low < low or body_high > high:
                contained = False
                break

        if contained:
            return {
                "index": idx,
                "time": dc["time"],
                "low": low,
                "high": high,
                "range": high - low,
                "contained_bars": newest - idx,
            }
    return None


def dc_breakout(candles, dc):
    """Return LONG/SHORT when the newest closed candle closes outside DC."""
    if not dc or not candles:
        return None

    close = float(candles[-1]["close"])
    if close > dc["high"]:
        return "LONG"
    if close < dc["low"]:
        return "SHORT"
    return None


def dc_context(candles, min_contained=3, lookback=8):
    """Return DC state and breakout direction for the latest closed candle."""
    dc = find_dominating_candle(
        candles, min_contained=min_contained, lookback=lookback
    )
    return {
        "dc": dc,
        "dc_valid": bool(dc),
        "dc_breakout": dc_breakout(candles, dc),
    }
