from execution.storage import EventStore


def test_event_store_persists_scan_order_and_outcome(tmp_path):
    store = EventStore(tmp_path / "trading.db")
    store.record_scan("2026-01-01T00:00:00+00:00", "EURUSD", {
        "status": "NO_TRADE", "reason_codes": ["HTF_NO_DIRECTIONAL_BIAS"]
    })
    store.record_order("2026-01-01T00:01:00+00:00", "EURUSD", {
        "status": "ORDER_ACKNOWLEDGED", "returncode": 0
    })
    store.record_selection("2026-01-01T00:00:30+00:00", "EURUSD", {
        "status": "SELECTED", "selected_signal_id": "EURUSD:t:variant-a",
        "selected_signal": {"variant": "variant-a"}, "conflict": None,
    })
    store.record_outcome("2026-01-01T01:00:00+00:00", "EURUSD", {
        "client_order_id": "CRT-EURUSD-1", "outcome": "WIN", "pnl_r": 1.5
    })
    scans = store.connection.execute("SELECT * FROM scans").fetchall()
    orders = store.connection.execute("SELECT * FROM order_events").fetchall()
    outcomes = store.connection.execute("SELECT * FROM trade_outcomes").fetchall()
    selections = store.connection.execute("SELECT * FROM signal_selections").fetchall()
    assert len(scans) == len(orders) == len(selections) == len(outcomes) == 1
    assert scans[0]["status"] == "NO_TRADE"
    assert orders[0]["status"] == "ORDER_ACKNOWLEDGED"
    assert selections[0]["selected_variant"] == "variant-a"
    assert selections[0]["selected_signal_id"] == "EURUSD:t:variant-a"
    assert outcomes[0]["outcome"] == "WIN"
    store.close()


def test_event_store_persists_oms_state_raw_event_and_halt(tmp_path):
    store = EventStore(tmp_path / "trading.db")
    store.record_order_intent("2026-01-01T00:00:00+00:00", {
        "internal_order_id": "int-1", "account_id": 7, "client_order_id": "client-1",
        "symbol": "EURUSD", "side": "BUY", "requested_volume": 1000,
    })
    store.record_order_state("2026-01-01T00:00:01+00:00", "int-1", "SUBMITTED")
    assert store.record_broker_event("2026-01-01T00:00:02+00:00", {
        "event_id": "evt-1", "account_id": 7, "internal_order_id": "int-1",
        "broker_order_id": 91, "execution_type": "ORDER_ACCEPTED",
        "raw_payload_hex": "abcd", "raw_event": {"executionType": "ORDER_ACCEPTED"},
    }, "ACKNOWLEDGED")
    assert not store.record_broker_event("2026-01-01T00:00:02+00:00", {
        "event_id": "evt-1", "raw_event": {},
    }, "ACKNOWLEDGED")
    store.record_order_state("2026-01-01T00:00:03+00:00", "int-1", "ACKNOWLEDGED",
                             broker_order_id=91)
    store.set_execution_halt(7, "2026-01-01T00:00:04+00:00", "mismatch")
    assert store.is_execution_halted(7)
    assert store.connection.execute("SELECT raw_payload_hex FROM broker_events").fetchone()[0] == "abcd"
    assert store.connection.execute("SELECT state FROM oms_orders").fetchone()[0] == "ACKNOWLEDGED"
    store.close()
