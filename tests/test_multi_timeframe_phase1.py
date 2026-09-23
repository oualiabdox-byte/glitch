from strategy.multi_timeframe import _displacement_qualified


def bar(o, h, l, c, i):
    return {"time": str(i), "open": o, "high": h, "low": l, "close": c}


def test_two_bar_displacement_is_accepted_without_weakening_single_bar_gate():
    candles = [
        bar(100.0, 100.8, 99.8, 100.7, 0),
        bar(100.7, 101.3, 100.5, 101.2, 1),
    ]
    qualified, mode = _displacement_qualified(candles, 1, atr=1.0)
    assert qualified is True
    assert mode == "TWO_BAR"


def test_small_single_bar_is_not_displacement():
    candles = [bar(100, 100.3, 99.9, 100.2, 0)]
    qualified, mode = _displacement_qualified(candles, 0, atr=1.0)
    assert qualified is False
    assert mode == "NONE"


from strategy.multi_timeframe import daily_bias


def test_daily_weak_location_requires_two_closes_and_body_direction():
    candles = [
        bar(10.0, 12.0, 8.0, 11.0, 0),
        bar(11.0, 11.8, 10.8, 11.2, 1),
    ]
    result = daily_bias(candles, tick_size=0.01)
    assert result.state == "BULLISH_WEAK"
    assert result.strength == "WEAK_LOCATION"


def test_daily_weak_location_does_not_accept_opposite_body():
    candles = [
        bar(10.0, 12.0, 8.0, 11.0, 0),
        bar(11.2, 11.8, 10.8, 11.0, 1),
    ]
    result = daily_bias(candles, tick_size=0.01)
    assert result.state == "NEUTRAL"
