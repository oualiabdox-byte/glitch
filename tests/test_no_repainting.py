from strategy.ict_bias import htf_bias_4h


def candle(o, h, l, c, t):
    return {"open": o, "high": h, "low": l, "close": c, "time": t}


def test_bias_is_deterministic_for_a_closed_slice():
    bars = [
        candle(1.10, 1.11, 1.09, 1.105, str(i))
        for i in range(24)
    ]
    first = htf_bias_4h(bars)
    assert first in (None, "LONG", "SHORT")
    assert htf_bias_4h(bars) == first
