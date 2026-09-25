from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from execution import demo_runner


def _stamp(delta: timedelta = timedelta(0)) -> str:
    return (datetime.now(timezone.utc) + delta).isoformat()


def test_setup_state_load_prunes_stale_setups_and_duplicate_signals(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    monkeypatch.setattr(demo_runner, "STATE_PATH", path)
    path.write_text(json.dumps({
        "setups": {
            "EURUSD": {"status": "WAITING_FOR_M5_CONFIRMATION", "updated_at": _stamp()},
            "GBPUSD": {"status": "WAITING_FOR_POI_TOUCH", "updated_at": _stamp(timedelta(days=-8))},
            "USDCHF": {"status": "TARGET_REACHED", "terminal_at": _stamp(timedelta(hours=-25))},
        },
        "signals": {
            "recent": {"signal_close_utc": _stamp()},
            "stale": {"signal_close_utc": _stamp(timedelta(days=-8))},
        },
    }))
    state = demo_runner._load_state()
    assert set(state["setups"]) == {"EURUSD"}
    assert set(state["signals"]) == {"recent"}


def test_setup_state_save_is_complete_and_replaces_destination_atomically(tmp_path, monkeypatch):
    path = tmp_path / "nested" / "state.json"
    monkeypatch.setattr(demo_runner, "STATE_PATH", path)
    payload = {"signals": {}, "setups": {"EURUSD": {"status": "WAITING_FOR_M5_CONFIRMATION"}}}
    demo_runner._save_state(payload)
    assert json.loads(path.read_text()) == payload
    assert not path.with_name(path.name + ".tmp").exists()


def test_transient_data_and_api_failures_preserve_setup_but_missing_premise_does_not():
    assert demo_runner._preserve_setup_on_scan_result({
        "status": "NO_TRADE", "reason_codes": ["STALE_M5_DATA"],
    })
    assert demo_runner._preserve_setup_on_scan_result({"status": "ERROR"})
    assert not demo_runner._preserve_setup_on_scan_result({
        "status": "NO_TRADE", "reason_codes": ["H1_STRUCTURE_UNCLEAR"],
    })
