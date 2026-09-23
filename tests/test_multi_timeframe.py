from strategy.multi_timeframe import confirmed_pivots, daily_bias, detect_fvg


def bar(o, h, l, c, i):
    return {"time": str(i), "open": o, "high": h, "low": l, "close": c}


def test_daily_bias_uses_closed_candle_and_next_session():
    candles = [bar(10, 12, 8, 10, 0), bar(10, 13, 9, 12.5, 1)]
    result = daily_bias(candles, tick_size=0.01)
    assert result.state == "BULLISH"
    assert result.reason == "CLOSE_ABOVE_PDH"
    assert result.availability_idx == 1
    assert result.effective_idx == 2


def test_daily_wick_only_is_not_breakout():
    candles = [bar(10, 12, 8, 10, 0), bar(10, 12.5, 9, 11, 1)]
    result = daily_bias(candles, tick_size=0.01)
    assert result.state == "NEUTRAL"


def test_confirmed_pivot_is_not_available_before_right_bars():
    candles = [bar(10, 11, 9, 10, i) for i in range(7)]
    candles[3] = bar(10, 15, 9, 10, 3)
    assert not confirmed_pivots(candles, end_idx=4, radius=2)
    pivots = confirmed_pivots(candles, end_idx=6, radius=2)
    assert any(p.side == "HIGH" and p.pivot_idx == 3 and p.confirmed_idx == 5 for p in pivots)


def test_future_bars_cannot_change_already_confirmed_pivot():
    base = [bar(10, 11, 9, 10, i) for i in range(9)]
    base[3] = bar(10, 15, 9, 10, 3)
    before = confirmed_pivots(base, end_idx=5, radius=2)
    changed = list(base)
    changed[8] = bar(10, 100, 9, 10, 8)
    after = confirmed_pivots(changed, end_idx=5, radius=2)
    assert before == after


def test_fvg_requires_completed_three_bar_triplet():
    candles = [bar(10, 10.2, 9.8, 10, 0), bar(10, 11, 10, 10.9, 1), bar(11, 12, 11.2, 11.8, 2)]
    zone = detect_fvg(candles, end_idx=2, tick_size=0.01, min_width_atr=0.0)
    assert zone is not None
    assert zone.side == "BULLISH"
    assert zone.created_idx == 2
