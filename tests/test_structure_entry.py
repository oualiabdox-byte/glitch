from strategy.structure_entry import find_entry


def bar(o, h, l, c, i):
    return {"open": o, "high": h, "low": l, "close": c, "time": str(i)}


def sample():
    return [
        bar(99, 100, 98, 99, 0),
        bar(99, 101, 98, 100, 1),
        bar(100, 102, 99, 101, 2),
        bar(101, 101, 97, 98, 3),
        bar(98, 100, 95, 98, 4),  # IDM sweep
        bar(98, 100, 97, 99, 5),
        bar(99, 101, 98, 100, 6),
        bar(100, 104.5, 99.5, 104, 7),  # MSS/BOS
        bar(104, 105.5, 103.5, 105, 8),  # confirmation
    ]


def test_structure_entry_is_known_only_after_confirmation_close():
    bars = sample()
    assert find_entry(bars, "LONG", end_idx=7, internal_lookback=3) is None
    signal = find_entry(bars, "LONG", end_idx=8, internal_lookback=3)
    assert signal is not None
    assert signal["idm_idx"] == 4
    assert signal["break_idx"] == 7
    assert signal["confirmation_idx"] == 8
    assert signal["mss"] is True
    assert signal["bos"] is True


def test_structure_entry_does_not_require_fvg_or_order_block():
    signal = find_entry(sample(), "LONG", end_idx=8, internal_lookback=3)
    assert signal["retest_exact"] is False
    assert signal["path"] == "CONTINUATION"
