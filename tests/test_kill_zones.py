from strategy import timing


def test_london_kill_zone_is_dst_aware():
    assert timing.in_kill_zone("2026-01-15T08:30:00Z", "london")
    assert timing.in_kill_zone("2026-07-15T07:30:00Z", "london")


def test_new_york_kill_zone_is_dst_aware():
    assert timing.in_kill_zone("2026-01-15T13:30:00Z", "new_york")
    assert timing.in_kill_zone("2026-07-15T12:30:00Z", "new_york")
