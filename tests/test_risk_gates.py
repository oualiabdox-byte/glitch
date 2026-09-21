from strategy import risk


def test_currency_exposure_counts_shared_currency():
    assert risk.currency_exposure_allowed(["EURUSD", "GBPUSD"], "AUDUSD", max_shared_currency=2) is False
    assert risk.currency_exposure_allowed(["EURUSD"], "GBPJPY", max_shared_currency=2) is True


def test_cooldown_blocks_recent_trade():
    assert risk.cooldown_clear(
        "2026-01-01T10:00:00Z",
        "2026-01-01T10:30:00Z",
        60,
    ) is False


def test_drawdown_guard_stops_after_threshold():
    assert risk.drawdown_guard(3.0, 8.0, 5.0) is False
    assert risk.drawdown_guard(3.1, 8.0, 5.0) is True
