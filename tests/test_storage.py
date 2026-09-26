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
