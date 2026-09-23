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
