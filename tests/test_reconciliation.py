from execution.reconciliation import Reconciler


def test_reconciliation_matches_normalized_order_snapshot():
    result = Reconciler().compare(
        7,
        [{"internal_order_id": "i1", "broker_order_id": 91,
          "state": "ACKNOWLEDGED", "executed_volume": 0}],
        [{"broker_order_id": 91, "state": "ACKNOWLEDGED", "executed_volume": 0}],
        [],
    )
    assert result.status == "MATCH"
    assert not result.halted


def test_reconciliation_mismatch_is_detected_without_repair():
    result = Reconciler().compare(
        7,
        [{"internal_order_id": "i1", "broker_order_id": 91,
          "state": "PARTIALLY_FILLED", "executed_volume": 400,
          "position_id": 12, "symbol": "EURUSD", "side": "BUY"}],
        [{"broker_order_id": 91, "state": "PARTIALLY_FILLED", "executed_volume": 200}],
        [{"symbol": "EURUSD", "side": "BUY", "volume": 0}],
    )
    assert result.status == "MISMATCH"
    assert any(item["type"] == "ORDER_FIELD_MISMATCH" for item in result.mismatches)
    assert any(item["type"] == "POSITION_VOLUME_MISMATCH" for item in result.mismatches)


def test_unexpected_broker_position_is_a_mismatch():
    result = Reconciler().compare(
        7, [], [], [{"symbol": "EURUSD", "side": "BUY", "volume": 1000}]
    )
    assert result.halted
    assert result.mismatches[0]["type"] == "UNEXPECTED_BROKER_POSITION"
