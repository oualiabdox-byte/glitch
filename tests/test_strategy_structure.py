from strategy import Strategy
from strategy.engine import find_latest_bos
from strategy.models import Candle
from strategy.structure import detect_structure_events, get_m5_execution_confirmation


def bar(i, o, h, l, c):
    return Candle(f"2026-01-01T{i:02d}:00:00Z", o, h, l, c)


def test_stale_bos_is_not_reused_as_current_entry():
    candles = [bar(i, 10, 10.5, 9.5, 10) for i in range(30)]
    candles[5] = bar(5, 10, 12, 9.8, 11)
    candles[6] = bar(6, 11, 11.2, 10.2, 10.8)
    candles[9] = bar(9, 10.8, 13, 10.7, 12.5)
    candles[10] = bar(10, 12.5, 12.6, 11.8, 12.1)
    events = detect_structure_events(candles, 2)
    assert events
    assert find_latest_bos(candles, [], "LONG", 2) is None


def test_strategy_uses_causal_structure_defaults():
    assert Strategy().swing_left == 3
    assert Strategy().swing_right == 3


def _m5_fixture(current_event: str | None = None) -> list[Candle]:
    candles = [bar(i, 10, 10.5, 9.5, 10) for i in range(30)]
    candles[5] = bar(5, 10, 12, 9.8, 11)
    candles[6] = bar(6, 11, 11.2, 10.2, 10.8)
    candles[9] = bar(9, 10.8, 13, 10.7, 12.5)
    candles[10] = bar(10, 12.5, 12.6, 11.8, 12.1)
    if current_event == "LONG":
        candles[-1] = bar(29, 12, 14, 11.5, 13.5)
    elif current_event == "SHORT":
        candles[-1] = bar(29, 10, 10.4, 8, 8.5)
    return candles


def _short_bos_fixture() -> list[Candle]:
    candles = [bar(i, 10, 10.5, 9.5, 10) for i in range(30)]
    candles[5] = bar(5, 10, 10.2, 8, 9)
    candles[6] = bar(6, 9, 9.8, 8.8, 9.2)
    candles[9] = bar(9, 9.2, 9.3, 7, 7.5)
    candles[10] = bar(10, 7.5, 8.2, 7.4, 7.8)
    candles[-1] = bar(29, 8, 8.4, 6, 6.5)
    return candles


def test_m5_long_stale_bos_is_not_actionable_for_h1_long():
    assert find_latest_bos(_m5_fixture(), [], "LONG", 2) is None


def test_authoritative_confirmation_reports_stale_event_and_shared_indices():
    confirmation = get_m5_execution_confirmation(_m5_fixture(), "LONG", 2)
    assert confirmation.valid is False
    assert confirmation.reason_codes == ("M5_EVENT_STALE",)
    assert confirmation.latest_event_index == 9
    assert confirmation.latest_closed_index == 29
    assert confirmation.event_is_latest_close is False


def test_m5_current_short_bos_or_choch_is_not_actionable_for_h1_long():
    candles = _m5_fixture("SHORT")
    assert find_latest_bos(candles, [], "LONG", 2) is None
    assert find_latest_bos(candles, [], "SHORT", 2) is not None


def test_authoritative_confirmation_rejects_current_opposite_choch():
    confirmation = get_m5_execution_confirmation(_m5_fixture("SHORT"), "LONG", 2)
    assert confirmation.valid is False
    assert confirmation.reason_codes == ("M5_EVENT_DIRECTION_MISMATCH",)
    assert confirmation.latest_event_side == "SHORT"
    assert confirmation.latest_event_type == "CHOCH"


def test_m5_current_long_bos_continues_long_validation():
    assert find_latest_bos(_m5_fixture("LONG"), [], "LONG", 2) is not None


def test_m5_current_long_bos_is_not_actionable_for_h1_short():
    assert find_latest_bos(_m5_fixture("LONG"), [], "SHORT", 2) is None


def test_m5_current_short_choch_continues_short_validation():
    assert find_latest_bos(_m5_fixture("SHORT"), [], "SHORT", 2) is not None


def test_authoritative_confirmation_accepts_current_short_bos():
    confirmation = get_m5_execution_confirmation(_short_bos_fixture(), "SHORT", 2)
    assert confirmation.valid is True
    assert confirmation.reason_codes == ()
    assert confirmation.latest_event_type == "BOS"
    assert confirmation.latest_event_index == confirmation.latest_closed_index == 29


def test_authoritative_confirmation_reports_no_structure_event():
    confirmation = get_m5_execution_confirmation(
        [bar(i, 10, 10.5, 9.5, 10) for i in range(30)], "LONG", 2,
    )
    assert confirmation.valid is False
    assert confirmation.reason_codes == ("M5_NO_STRUCTURE_EVENT",)
    assert confirmation.latest_event is None


def test_authoritative_confirmation_does_not_fall_back_to_older_long_event():
    confirmation = get_m5_execution_confirmation(_m5_fixture("SHORT"), "LONG", 2)
    assert confirmation.latest_event_side == "SHORT"
    assert confirmation.latest_event_index == 29
    assert confirmation.reason_codes == ("M5_EVENT_DIRECTION_MISMATCH",)
