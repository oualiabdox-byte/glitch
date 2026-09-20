"""Order Block detection — opposing candle before displacement (ICT 2022 model)."""


def find_order_block(candles_1h, fvg_result):
    """Find the opposing candle (OB) that appears before the displacement/FVG.
    Only uses data before the FVG creator candle — no repaint."""
    if not fvg_result:
        return None
    creator_idx = fvg_result["creator_idx"]
    if creator_idx < 1:
        return None
    # The opposing candle is the candle before the FVG creator (index - 1 relative to window)
    # Actually in full 1h data: the candle before the displacement is at creator_idx - 1
    # Let's find it in the full dataset
    if creator_idx < 1:
        return None
    # We need to look at the candle immediately before the displacement
    # The FVG requires a-1, b, c — so the OB is candle a-1's opposing candle
    # For simplicity: the opposing candle before the FVG formation
    # In ICT, the OB is the last opposing candle before displacement
    # We'll approximate: candle at creator_idx - 2 or earlier opposing candles
    # Let's scan backward from creator_idx - 1 to find opposing candle
    for j in range(creator_idx - 1, max(0, creator_idx - 10), -1):
        c = candles_1h[j]
        # Bullish setup: opposing candle = SHORT candle (close < open)
        # Bearish setup: opposing candle = LONG candle (close > open)
        side = fvg_result["side"]
        if side == "LONG" and c["close"] < c["open"]:
            return {"side": "LONG", "top": c["high"], "bottom": c["low"],
                    "time": c["time"], "creator": c}
        if side == "SHORT" and c["close"] > c["open"]:
            return {"side": "SHORT", "top": c["low"], "bottom": c["high"],
                    "time": c["time"], "creator": c}
    return None
