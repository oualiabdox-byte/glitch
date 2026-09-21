from strategy.fvg import find_fvg


def candle(o, h, l, c, t):
    return {"open": o, "high": h, "low": l, "close": c, "time": t}


def warmup(n=15):
    return [candle(1.1000, 1.1010, 1.0990, 1.1000, str(i)) for i in range(n)]


def test_fvg_uses_only_explicitly_closed_boundary():
    bars = warmup()
    bars[11] = candle(1.1000, 1.1010, 1.0990, 1.1005, "11")
    bars[12] = candle(1.1005, 1.1050, 1.1000, 1.1045, "12")
    bars[13] = candle(1.1045, 1.1100, 1.1060, 1.1080, "13")
    # This final bar would create a different future pattern if it were used.
    bars[14] = candle(1.1080, 1.1200, 1.1070, 1.1090, "14")

    zone = find_fvg(bars, required_side="LONG", end_idx=13)
    assert zone is not None
    assert zone["creator_idx"] == 12
    assert zone["confirmation_idx"] == 13


def test_unclosed_future_bar_is_not_used():
    bars = warmup()
    bars[12] = candle(1.1000, 1.1010, 1.1000, 1.1005, "12")
    bars[13] = candle(1.1005, 1.1030, 1.1020, 1.1025, "13")
    bars[14] = candle(1.1025, 1.1200, 1.1050, 1.1150, "14")

    assert find_fvg(bars, required_side="LONG", end_idx=13) is None
