"""POI mitigation state helpers.

Fresh means price has not previously closed through the invalidation side of
the zone. This is intentionally separate from entry generation.
"""

def zone_mitigated(candles, zone, side, end_idx=None):
    if not zone:
        return False
    end = len(candles) - 1 if end_idx is None else min(end_idx, len(candles) - 1)
    for i in range(zone["idx"] + 1, end + 1):
        c = candles[i]
        if side == "LONG" and c["close"] < zone["bottom"]:
            return True
        if side == "SHORT" and c["close"] > zone["top"]:
            return True
    return False

def first_retest(candles, zone, side):
    if not zone or zone["idx"] >= len(candles) - 1:
        return False
    for c in candles[zone["idx"] + 1:-1]:
        if side == "LONG" and c["low"] <= zone["top"]:
            return False
        if side == "SHORT" and c["high"] >= zone["bottom"]:
            return False
    cur = candles[-1]
    return (
        cur["low"] <= zone["top"] and cur["close"] >= zone["bottom"]
        if side == "LONG"
        else cur["high"] >= zone["bottom"] and cur["close"] <= zone["top"]
    )
