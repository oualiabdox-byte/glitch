from datetime import datetime, timezone

from execution.execution_guard import evaluate_execution


def signal(**overrides):
    value = {
        "pair": "EURUSD",
        "side": "LONG",
        "entry_price": 1.1000,
        "stop_price": 1.0980,
        "target_price": 1.1040,
        "timestamp": "2026-09-28T12:00:00+00:00",
    }
    value.update(overrides)
    return value


def test_execution_guard_uses_executable_ask_for_long():
    result = evaluate_execution(
        signal(),
        bid=1.1010,
        ask=1.1011,
        now=datetime(2026, 9, 28, 12, 1, tzinfo=timezone.utc),
        max_signal_age_seconds=300,
        max_spread_pips=3,
        max_price_drift_pips=20,
    )
    assert result.expected_fill == 1.1011
    assert result.stop_distance == 1.1011 - 1.0980
    assert result.target_distance == 1.1040 - 1.1011
    assert result.execution_rr is not None


def test_execution_guard_rejects_spread():
    result = evaluate_execution(
        signal(),
        bid=1.1000,
        ask=1.1008,
        now=datetime(2026, 9, 28, 12, 1, tzinfo=timezone.utc),
        max_spread_pips=3,
    )
    assert not result.approved
    assert "SPREAD_TOO_WIDE" in result.reason_codes


def test_execution_guard_rejects_stale_signal():
    result = evaluate_execution(
        signal(),
        bid=1.1000,
        ask=1.1001,
        now=datetime(2026, 9, 28, 13, 0, tzinfo=timezone.utc),
        max_signal_age_seconds=300,
    )
    assert not result.approved
    assert "SIGNAL_TOO_OLD" in result.reason_codes


def test_execution_guard_rejects_collapsed_target():
    result = evaluate_execution(
        signal(),
        bid=1.1045,
        ask=1.1046,
        now=datetime(2026, 9, 28, 12, 1, tzinfo=timezone.utc),
    )
    assert not result.approved
    assert "TARGET_INVALIDATED_AT_EXECUTION" in result.reason_codes
