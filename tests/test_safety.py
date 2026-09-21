from strategy import safety


def test_abnormal_volatility_guard():
    bars = []
    for i in range(25):
        bars.append({
            "time": str(i),
            "open": 1.0,
            "high": 1.001,
            "low": 0.999,
            "close": 1.0,
        })
    bars[-1]["high"] = 1.006
    bars[-1]["low"] = 0.994
    assert safety.abnormal_volatility(bars, max_ratio=2.5) is True


def test_news_blackout_filters_currency():
    event = {"time_utc": "2026-01-15T10:00:00Z", "currencies": ["USD"]}
    assert safety.news_blocked(
        "2026-01-15T09:30:00Z",
        "EURUSD",
        [event],
        pause_before_minutes=45,
        pause_after_minutes=20,
    )
    assert not safety.news_blocked(
        "2026-01-15T09:30:00Z",
        "EURGBP",
        [event],
        pause_before_minutes=45,
        pause_after_minutes=20,
    )


def test_signal_once_per_bar():
    assert safety.signal_once_per_bar(None, "2026-01-15T10:00:00Z") is True
    assert safety.signal_once_per_bar("2026-01-15T10:00:00Z", "2026-01-15T10:00:00Z") is False
