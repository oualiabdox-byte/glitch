"""Fair Value Gap detection with causal lifecycle validation."""

def _atr(candles, end_idx, period=14):
    start = max(1, end_idx - period)
    if start >= end_idx:
        return 0.0
    trs = []
    for i in range(start, end_idx):
        h, l = candles[i]["high"], candles[i]["low"]
        pc = candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else 0.0


def find_fvg(candles_1h, start_idx=0, min_gap_atr=0.0,
             required_side=None, displacement_min_atr=0.0):
    if len(candles_1h) < 3:
        return None

    for i in range(len(candles_1h) - 2, start_idx, -1):
        a, b, c = candles_1h[i - 1], candles_1h[i], candles_1h[i + 1]
        atr = _atr(candles_1h, i)
        if atr <= 0:
            continue

        side = None
        bottom = top = None
        if b["close"] > b["open"] and a["high"] < c["low"]:
            side, bottom, top = "LONG", a["high"], c["low"]
        elif b["close"] < b["open"] and a["low"] > c["high"]:
            side, bottom, top = "SHORT", c["high"], a["low"]

        if side is None or (required_side and side != required_side):
            continue

        gap_size = top - bottom
        if gap_size < atr * min_gap_atr:
            continue

        body = abs(b["close"] - b["open"])
        if displacement_min_atr and body < atr * displacement_min_atr:
            continue

        return {
            "side": side, "bottom": bottom, "top": top,
            "gap_size": gap_size, "gap_atr": gap_size / atr,
            "creator_idx": i, "creator_time": b["time"],
            "confirmation_idx": i + 1, "confirmation_time": c["time"],
        }
    return None


def is_fresh_retest(candles, fvg_result, current_idx=None):
    """Require the first post-confirmation interaction to be the current bar."""
    if not fvg_result:
        return False
    current_idx = len(candles) - 1 if current_idx is None else current_idx
    start = fvg_result["confirmation_idx"] + 1
    if current_idx <= start:
        return False

    bottom, top = fvg_result["bottom"], fvg_result["top"]
    for i in range(start, current_idx):
        c = candles[i]
        if c["high"] >= bottom and c["low"] <= top:
            return False

    current = candles[current_idx]
    if fvg_result["side"] == "LONG":
        return current["low"] <= top and current["close"] >= bottom
    return current["high"] >= bottom and current["close"] <= top


def fvg_in_window(candles_1h, window_start_idx, window_end_idx, side):
    window = candles_1h[window_start_idx:window_end_idx + 1]
    return find_fvg(window, required_side=side)
