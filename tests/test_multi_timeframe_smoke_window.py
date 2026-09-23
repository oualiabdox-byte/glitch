from backtest.multi_timeframe_smoke import weekday_days_in_window


def bar(day):
    return {"time": f"{day}T12:00:00Z"}


def test_weekday_selection_is_half_open_and_excludes_out_of_window_bars():
    bars = [
        bar("2026-09-08"),
        bar("2026-09-09"),
        bar("2026-09-12"),  # Saturday
        bar("2026-09-22"),
        bar("2026-09-23"),  # end boundary: excluded
    ]
    assert weekday_days_in_window(
        bars, "2026-09-09T00:00:00Z", "2026-09-23T00:00:00Z"
    ) == ["2026-09-09", "2026-09-22"]
