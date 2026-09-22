from strategy.breakout_retest import find_breakout_retest


def candle(open_, high, low, close, time):
    return {"open": open_, "high": high, "low": low, "close": close, "time": time}


def setup_bars():
    return [
        candle(9.0, 10.0, 8.0, 9.0, "0"),
        candle(9.0, 11.0, 8.5, 10.0, "1"),
        candle(10.0, 12.0, 9.5, 11.0, "2"),
        candle(11.0, 10.5, 8.5, 9.0, "3"),
        candle(9.0, 9.5, 7.5, 8.0, "4"),
        candle(11.0, 13.2, 10.8, 13.0, "5"),
        candle(12.5, 12.5, 11.9, 12.2, "6"),
        candle(12.2, 12.9, 12.1, 12.8, "7"),
    ]


def test_breakout_retest_requires_closed_confirmation_bar():
    bars = setup_bars()
    assert find_breakout_retest(
        bars, "LONG", end_idx=6, swing_length=2, breakout_body_atr=0.5
    ) is None

    signal = find_breakout_retest(
        bars, "LONG", end_idx=7, swing_length=2, breakout_body_atr=0.5
    )
    assert signal is not None
    assert signal["breakout_idx"] == 5
    assert signal["retest_idx"] == 6
    assert signal["confirmation_idx"] == 7
    assert signal["level"] == 12.0


def test_breakout_retest_does_not_use_future_bars_for_level():
    bars = setup_bars()
    signal = find_breakout_retest(
        bars, "LONG", end_idx=7, swing_length=2, breakout_body_atr=0.5
    )
    assert signal["level_time"] == "2"
    bars[4]["high"] = 20.0
    assert find_breakout_retest(
        bars, "LONG", end_idx=5, swing_length=2, breakout_body_atr=0.5
    ) is None
