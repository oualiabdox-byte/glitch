from backtest.validation import build_walk_forward_windows


def test_walk_forward_windows_are_chronological_and_embargoed():
    windows = build_walk_forward_windows(list(range(20)), train_bars=8, test_bars=4, step_bars=4, embargo_bars=2)
    assert windows[0].train_start == 0
    assert windows[0].train_end == 8
    assert windows[0].test_start == 10
    assert windows[0].test_end == 14
    assert windows[1].train_start == 4
    assert windows[-1].test_end <= 20


def test_walk_forward_rejects_invalid_sizes():
    try:
        build_walk_forward_windows(range(10), train_bars=0, test_bars=2)
    except ValueError as exc:
        assert "train_bars" in str(exc)
    else:
        raise AssertionError("invalid train size should fail")
