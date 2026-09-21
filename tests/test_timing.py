from strategy import timing


def test_london_open_is_dst_aware():
    winter = timing.session_context("2026-01-15T08:00:00Z")
    summer = timing.session_context("2026-07-15T07:00:00Z")
    assert winter.session == "london"
    assert summer.session == "london"
    assert winter.phase == "open"
    assert summer.phase == "open"


def test_overlap_is_detected_from_named_local_sessions():
    ctx = timing.session_context("2026-01-15T14:00:00Z")
    assert ctx.session == "overlap"
    assert ctx.overlap is True


def test_session_delay_is_causal():
    assert timing.after_session_open("2026-01-15T08:00:00Z", 30) is False
    assert timing.after_session_open("2026-01-15T08:30:00Z", 30) is True
