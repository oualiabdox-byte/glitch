import pytest

from execution.oms import InvalidTransition, OMS, OrderIntent, OrderState


def make_oms():
    oms = OMS(account_id=7)
    oms.create_intent(OrderIntent("int-1", 7, "EURUSD", "BUY", 1000, "client-1"))
    return oms


def test_broker_event_is_distinct_from_resulting_state_and_partial_fill_is_accounted():
    oms = make_oms()
    oms.mark_submitted("int-1")
    accepted = oms.apply_broker_event("int-1", {
        "event_id": "evt-accepted", "execution_type": "ORDER_ACCEPTED",
        "broker_order_id": 91,
    })
    assert accepted.resulting_state is OrderState.ACKNOWLEDGED
    partial = oms.apply_broker_event("int-1", {
        "event_id": "deal-1", "execution_type": "ORDER_PARTIAL_FILL",
        "broker_order_id": 91, "position_id": 12,
        "last_volume": 400, "execution_price": 1.1,
    })
    assert partial.resulting_state is OrderState.PARTIALLY_FILLED
    assert oms.orders["int-1"].executed_volume == 400
    assert oms.orders["int-1"].remaining_volume == 600


def test_duplicate_execution_event_is_idempotent():
    oms = make_oms()
    oms.mark_submitted("int-1")
    event = {"event_id": "deal-1", "execution_type": "ORDER_PARTIAL_FILL", "last_volume": 400}
    first = oms.apply_broker_event("int-1", event)
    second = oms.apply_broker_event("int-1", event)
    assert first.applied
    assert second.duplicate
    assert oms.orders["int-1"].executed_volume == 400


def test_unknown_halts_account_and_is_not_resubmittable():
    oms = make_oms()
    oms.mark_submitted("int-1")
    result = oms.mark_unknown("int-1", "connection lost after send")
    assert result.resulting_state is OrderState.UNKNOWN
    assert oms.halted
    with pytest.raises(RuntimeError, match="EXECUTION_HALT"):
        oms.create_intent(OrderIntent("int-2", 7, "EURUSD", "BUY", 1000, "client-2"))


def test_failed_is_only_for_proven_pre_broker_failure():
    oms = make_oms()
    result = oms.mark_failed("int-1", "request serialization failed before send")
    assert result.resulting_state is OrderState.FAILED
    assert not oms.halted


def test_invalid_transition_is_rejected():
    oms = make_oms()
    with pytest.raises(InvalidTransition):
        oms.apply_broker_event("int-1", {
            "event_id": "fill-1", "execution_type": "ORDER_FILLED",
        })
