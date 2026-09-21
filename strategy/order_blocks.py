"""Causal Order Block detection with freshness/mitigation checks."""

def find_order_block(candles_1h, fvg_result, lookback=10):
    if not fvg_result:
        return None
    creator_idx = fvg_result["creator_idx"]
    if creator_idx < 2:
        return None

    side = fvg_result["side"]
    start = max(0, creator_idx - lookback)
    for j in range(creator_idx - 1, start - 1, -1):
        c = candles_1h[j]
        if side == "LONG" and c["close"] < c["open"]:
            return _build(candles_1h, j, side)
        if side == "SHORT" and c["close"] > c["open"]:
            return _build(candles_1h, j, side)
    return None


def _build(candles, idx, side):
    zone = {
        "side": side, "top": candles[idx]["high"], "bottom": candles[idx]["low"],
        "time": candles[idx]["time"], "creator": candles[idx], "idx": idx,
    }
    return zone


def is_fresh_retest(candles, order_block, current_idx=None):
    if not order_block:
        return False
    current_idx = len(candles) - 1 if current_idx is None else current_idx
    if current_idx <= order_block["idx"] + 1:
        return False

    bottom, top = order_block["bottom"], order_block["top"]
    for i in range(order_block["idx"] + 1, current_idx):
        c = candles[i]
        if c["high"] >= bottom and c["low"] <= top:
            return False

    c = candles[current_idx]
    return c["high"] >= bottom and c["low"] <= top
