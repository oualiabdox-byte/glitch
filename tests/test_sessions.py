from strategy import timing


def test_london_and_new_york_sessions_are_detected():
    assert timing.session_at("2026-01-15T09:00:00Z") == "london"
    assert timing.session_at("2026-01-15T15:00:00Z") == "overlap"


def test_non_session_returns_other():
    assert timing.session_at("2026-01-15T22:00:00Z") == "other"
