from strategy.ote import compute_ote, price_in_ote
from strategy.breaker_blocks import find_breaker_block
from strategy.mitigation import zone_mitigated

def candle(t,o,h,l,c):
    return {"time": t, "open": o, "high": h, "low": l, "close": c}

def test_ote_long_zone():
    z = compute_ote(100, 110, "LONG")
    assert z["bottom"] < z["mid"] < z["top"]
    assert price_in_ote(z["mid"], z)

def test_breaker_after_ob_invalidation():
    candles = [
        candle(1, 105, 106, 100, 104),
        candle(2, 104, 105, 99, 103),
        candle(3, 103, 104, 95, 96),
    ]
    ob = {"idx": 0, "time": 1, "top": 106, "bottom": 100}
    br = find_breaker_block(candles, ob, "LONG", break_idx=2)
    assert br is not None

def test_mitigation_is_causal():
    candles = [candle(1, 100, 105, 99, 103), candle(2, 103, 104, 98, 99)]
    zone = {"idx": 0, "top": 105, "bottom": 100}
    assert zone_mitigated(candles, zone, "LONG")
