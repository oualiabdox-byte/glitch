from strategy.fvg import find_fvg, is_near_or_continuation_retest
from strategy.liquidity import equal_highs_lows
from strategy.order_blocks import find_order_block


def candle(o, h, l, c, t):
    return {"open": o, "high": h, "low": l, "close": c, "time": t}


def warmup(n=15):
    return [candle(1.1000, 1.1010, 1.0990, 1.1000, str(i)) for i in range(n)]


def test_equal_liquidity_is_fx_calibrated():
    bars = [
        candle(1.1000, 1.2000, 1.0900, 1.1000, "1"),
        candle(1.1000, 1.2010, 1.0900, 1.1000, "2"),
    ]
    eqh, _ = equal_highs_lows(bars)
    assert eqh == []


def test_bullish_fvg_and_short_ob_bounds():
    bars = warmup()
    bars[11] = candle(1.1000, 1.1010, 1.0990, 1.1005, "11")
    bars[12] = candle(1.1005, 1.1050, 1.1000, 1.1045, "12")
    bars[13] = candle(1.1045, 1.1100, 1.1060, 1.1080, "13")
    zone = find_fvg(bars, required_side="LONG", end_idx=13)
    assert zone is not None
    ob = find_order_block(bars, zone)
    assert ob is not None
    assert ob["bottom"] <= ob["top"]


def test_fvg_uses_closed_three_candle_sequence():
    bars = warmup()
    bars[11] = candle(1.1000, 1.1010, 1.0990, 1.1005, "11")
    bars[12] = candle(1.1005, 1.1030, 1.1000, 1.1025, "12")
    bars[13] = candle(1.1025, 1.1060, 1.1040, 1.1050, "13")
    zone = find_fvg(bars, required_side="LONG", end_idx=13)
    assert zone is not None
    assert zone["creator_idx"] == 12


def test_near_retest_is_bounded_and_causal():
    bars = warmup()
    bars[11] = candle(1.1000, 1.1010, 1.0990, 1.1005, "11")
    bars[12] = candle(1.1005, 1.1030, 1.1000, 1.1025, "12")
    bars[13] = candle(1.1025, 1.1060, 1.1040, 1.1050, "13")
    zone = {
        "side": "LONG", "bottom": 1.101, "top": 1.104,
        "confirmation_idx": 13,
    }
    bars.append(candle(1.1050, 1.1050, 1.1041, 1.1042, "14"))
    assert is_near_or_continuation_retest(
        bars, zone, current_idx=15, tolerance=0.0002, max_wait_bars=2
    ) is True
    assert is_near_or_continuation_retest(
        bars, zone, current_idx=15, tolerance=0.0002, max_wait_bars=1
    ) is False
