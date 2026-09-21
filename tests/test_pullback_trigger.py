from strategy import ict_hybrid


def bar(i, close, high=None, low=None):
    return {
        "time": i,
        "open": close,
        "high": close if high is None else high,
        "low": close if low is None else low,
        "close": close,
    }


def test_pullback_trigger_long_closes_above_previous_high():
    recent = [
        bar(0, 100, 101, 99),
        bar(1, 100.5, 101.0, 99.5),
        bar(2, 102.0, 102.5, 100.0),
    ]
    assert ict_hybrid._pullback_trigger(recent, "LONG") is True


def test_pullback_trigger_short_closes_below_previous_low():
    recent = [
        bar(0, 100, 101, 99),
        bar(1, 99.5, 100.0, 99.0),
        bar(2, 97.5, 99.0, 97.0),
    ]
    assert ict_hybrid._pullback_trigger(recent, "SHORT") is True


def test_pullback_trigger_rejects_non_break():
    recent_long = [
        bar(0, 100, 101, 99),
        bar(1, 100.5, 101.0, 99.5),
        bar(2, 100.8, 101.2, 99.8),
    ]
    recent_short = [
        bar(0, 100, 101, 99),
        bar(1, 99.5, 100.0, 99.0),
        bar(2, 99.2, 99.8, 98.8),
    ]

    assert ict_hybrid._pullback_trigger(recent_long, "LONG") is False
    assert ict_hybrid._pullback_trigger(recent_short, "SHORT") is False


def test_pullback_trigger_is_indicator_free():
    recent = [
        bar(0, 100, 101, 99),
        bar(1, 100.5, 101.0, 99.5),
        bar(2, 102.0, 102.5, 100.0),
    ]
    # The helper only needs OHLC; no indicator series or external state.
    assert ict_hybrid._pullback_trigger(recent, "LONG")
