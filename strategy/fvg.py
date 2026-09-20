"""Fair Value Gap detection — only historical candles, no repaint."""


def find_fvg(candles_1h, start_idx=0):
    """Find the first FVG formed by a displacement candle in the window.
    Requires 3 candles (before, displacement, after) — all must be closed."""
    if len(candles_1h) < 3:
        return None
    for i in range(start_idx + 1, len(candles_1h) - 1):
        a, b, c = candles_1h[i - 1], candles_1h[i], candles_1h[i + 1]
        # Bullish FVG: displacement candle close > open, previous high < next low
        if b["close"] > b["open"] and a["high"] < c["low"]:
            gap_size = abs(a["high"] - c["low"])
            if gap_size > 0:
                return {"side": "LONG", "bottom": a["high"], "top": c["low"],
                        "creator_idx": i, "creator_time": b["time"]}
        # Bearish FVG: displacement candle close < open, previous low > next high
        if b["close"] < b["open"] and a["low"] > c["high"]:
            gap_size = abs(a["low"] - c["high"])
            if gap_size > 0:
                return {"side": "SHORT", "bottom": c["high"], "top": a["low"],
                        "creator_idx": i, "creator_time": b["time"]}
    return None


def fvg_in_window(candles_1h, window_start_idx, window_end_idx, side):
    """Find any FVG matching the direction within a window index range."""
    window = candles_1h[window_start_idx:window_end_idx + 1]
    return find_fvg(window)
