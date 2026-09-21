from datetime import datetime, timezone

from backtest.ctrader_runner import bar_close_time, h4_until


def bar(t):
    return {
        "time": t,
        "open": 1.1,
        "high": 1.2,
        "low": 1.0,
        "close": 1.15,
    }


def test_h1_signal_timestamp_is_bar_close():
    assert bar_close_time(bar("2026-01-01T10:00:00Z"), 1) == datetime(
        2026, 1, 1, 11, tzinfo=timezone.utc
    )


def test_h4_context_excludes_unclosed_h4_bar():
    h4 = [
        bar("2026-01-01T00:00:00Z"),
        bar("2026-01-01T04:00:00Z"),
        bar("2026-01-01T08:00:00Z"),
    ]
    visible = h4_until(h4, "2026-01-01T08:00:00Z")
    assert [x["time"] for x in visible] == [
        "2026-01-01T00:00:00Z",
        "2026-01-01T04:00:00Z",
    ]
