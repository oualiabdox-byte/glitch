from strategy.fvg import find_fvg
from strategy.liquidity import equal_highs_lows
from strategy.order_blocks import find_order_block


def candle(o, h, l, c, t):
    return {"open": o, "high": h, "low": l, "close": c, "time": t}


def test_equal_liquidity_is_fx_calibrated():
    bars = [
        candle(1.1000, 1.2000, 1.0900, 1.1000, "1"),
        candle(1.1000, 1.2010, 1.0900, 1.1000, "2"),
    ]
    eqh, _ = equal_highs_lows(bars)
    assert eqh == []


def test_bullish_fvg_and_short_ob_bounds():
    bars = [
        candle(1.1000, 1.1050, 1.0950, 1.1020, "0"),
        candle(1.1020, 1.1030, 1.1000, 1.1010, "1"),
        candle(1.1010, 1.1100, 1.1060, 1.1090, "2"),
        candle(1.1090, 1.1150, 1.1080, 1.1140, "3"),
        candle(1.1140, 1.1180, 1.1130, 1.1170, "4"),
    ]
    zone = find_fvg(bars, required_side="LONG")
    assert zone is not None
    ob = find_order_block(bars, zone)
    assert ob is not None
    assert ob["bottom"] <= ob["top"]


def test_fvg_uses_closed_three_candle_sequence():
    bars = [
        candle(1.1000, 1.1010, 1.0990, 1.1005, "0"),
        candle(1.1005, 1.1030, 1.1000, 1.1025, "1"),
        candle(1.1025, 1.1060, 1.1040, 1.1050, "2"),
    ]
    zone = find_fvg(bars, required_side="LONG")
    assert zone is not None
    assert zone["creator_idx"] == 1
