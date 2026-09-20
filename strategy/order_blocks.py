"""Order Block detection — simplified, causal SMC/ICT POI."""


def find_order_block(candles_1h, fvg_result):
    """Find the nearest opposing candle before the FVG displacement.

    Returned top/bottom are always normalized so bottom <= top. No future
    candles beyond the FVG creator are inspected.
    """
    if not fvg_result:
        return None

    creator_idx = fvg_result["creator_idx"]
    if creator_idx < 2:
        return None

    side = fvg_result["side"]
    for j in range(creator_idx - 1, max(-1, creator_idx - 10), -1):
        c = candles_1h[j]
        if side == "LONG" and c["close"] < c["open"]:
            return {
                "side": "LONG",
                "top": c["high"],
                "bottom": c["low"],
                "time": c["time"],
                "creator": c,
                "idx": j,
            }
        if side == "SHORT" and c["close"] > c["open"]:
            return {
                "side": "SHORT",
                "top": c["high"],
                "bottom": c["low"],
                "time": c["time"],
                "creator": c,
                "idx": j,
            }
    return None
