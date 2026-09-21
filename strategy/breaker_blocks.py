"""Breaker Block detection — causal, optional SMC confluence.

A breaker is treated as a previously identified OB whose polarity has been
invalidated by a confirmed close through its far side. It is a context/POI
component only; the hybrid strategy does not require it by default.
"""

def find_breaker_block(candles, ob, side, break_idx=None):
    if not ob:
        return None
    end = len(candles) - 1 if break_idx is None else min(break_idx, len(candles) - 1)
    if end <= ob["idx"]:
        return None

    zone = {"top": ob["top"], "bottom": ob["bottom"], "idx": ob["idx"], "time": ob["time"]}
    if side == "LONG":
        broken = any(candles[i]["close"] < zone["bottom"] for i in range(ob["idx"] + 1, end + 1))
        if not broken:
            return None
        return {**zone, "side": "LONG", "breaker_side": "SHORT", "kind": "BULLISH_OB_TO_BEARISH_BREAKER"}
    if side == "SHORT":
        broken = any(candles[i]["close"] > zone["top"] for i in range(ob["idx"] + 1, end + 1))
        if not broken:
            return None
        return {**zone, "side": "SHORT", "breaker_side": "LONG", "kind": "BEARISH_OB_TO_BULLISH_BREAKER"}
    return None
