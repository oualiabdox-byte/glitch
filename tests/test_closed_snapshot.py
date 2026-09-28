from datetime import datetime, timezone

from data.closed_snapshot import ClosedBarSnapshot, candle_is_closed


def test_closed_bar_boundary_is_exact():
    candle = {"time": "2026-09-28T12:00:00+00:00"}
    assert not candle_is_closed(
        candle, "M5", datetime(2026, 9, 28, 12, 4, 59, tzinfo=timezone.utc)
    )
    assert candle_is_closed(
        candle, "M5", datetime(2026, 9, 28, 12, 5, tzinfo=timezone.utc)
    )


def test_snapshot_excludes_future_bars():
    snapshot = ClosedBarSnapshot.build(
        as_of=datetime(2026, 9, 28, 12, 5, tzinfo=timezone.utc),
        candles_by_timeframe={
            "M5": [
                {"time": "2026-09-28T12:00:00+00:00"},
                {"time": "2026-09-28T12:05:00+00:00"},
            ]
        },
    )
    assert [row["time"] for row in snapshot.candles("M5")] == [
        "2026-09-28T12:00:00+00:00"
    ]
