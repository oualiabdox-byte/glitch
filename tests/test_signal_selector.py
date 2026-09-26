from __future__ import annotations

import inspect
import json

from execution import bot_main, demo_order, demo_runner
from strategy import select_signals, signal_identity, variants_for_pair

EUR_A = "eurusd_swing3_choch_or_bos"
EUR_B = "eurusd_swing2_choch_or_bos"
EUR_VARIANTS = (EUR_A, EUR_B)
STAMP = "2026-09-26T12:00:00+00:00"


def _signal(variant, side="LONG", *, rr=2.0, score=None, stamp=STAMP):
    row = {
        "pair": "EURUSD", "variant": variant, "status": "SIGNAL_ONLY",
        "side": side, "timestamp": stamp, "signal_close_utc": stamp, "rr": rr,
        "entry_price": 1.1, "stop_price": 1.09, "target_price": 1.12,
        "evidence": {"h1_structure": {"state": "BULLISH"}},
    }
    if score is not None:
        row["quality_score"] = score
    return row


def _no_trade(variant):
    return {"pair": "EURUSD", "variant": variant, "status": "NO_TRADE"}


def test_one_buy_and_one_sell_signal_are_selected():
    buy = select_signals([_signal(EUR_A, "BUY")], expected_variants=(EUR_A,))
    sell = select_signals([_signal(EUR_A, "SELL")], expected_variants=(EUR_A,))
    assert buy["status"] == sell["status"] == "SELECTED"
    assert buy["selected_signal"]["side"] == "BUY"
    assert sell["selected_signal"]["side"] == "SELL"


def test_buy_plus_no_trade_selects_buy():
    result = select_signals([_signal(EUR_A, "BUY"), _no_trade(EUR_B)],
                            expected_variants=EUR_VARIANTS)
    assert result["status"] == "SELECTED"
    assert result["selected_signal"]["side"] == "BUY"


def test_same_direction_signals_select_deterministically_independent_of_order():
    rows = [_signal(EUR_A, "BUY", rr=2), _signal(EUR_B, "LONG", rr=3)]
    forward = select_signals(rows, expected_variants=EUR_VARIANTS)
    reverse = select_signals(reversed(rows), expected_variants=EUR_VARIANTS)
    assert forward["status"] == reverse["status"] == "SELECTED"
    assert forward["selected_signal_id"] == reverse["selected_signal_id"]
    assert forward["selected_signal"]["variant"] == EUR_B


def test_same_side_ties_use_stable_variant_name_not_dictionary_order():
    rows = [_signal(EUR_B, "SELL"), _signal(EUR_A, "SELL")]
    first = select_signals(rows, expected_variants=EUR_VARIANTS)
    second = select_signals(reversed(rows), expected_variants=EUR_VARIANTS)
    assert first["selected_signal"]["variant"] == second["selected_signal"]["variant"] == EUR_B


def test_existing_quality_and_rr_break_ties_without_creating_strategy_rules():
    quality = select_signals([
        _signal(EUR_A, "LONG", rr=2, score=0.7),
        _signal(EUR_B, "LONG", rr=4, score=0.8),
    ], expected_variants=EUR_VARIANTS)
    rr = select_signals([
        _signal(EUR_A, "LONG", rr=3), _signal(EUR_B, "LONG", rr=4),
    ], expected_variants=EUR_VARIANTS)
    assert quality["selected_signal"]["variant"] == EUR_B
    assert rr["selected_signal"]["variant"] == EUR_B
    assert quality["historical_validation_confidence_used"] is False


def test_buy_and_sell_candidates_produce_explicit_conflict():
    result = select_signals([_signal(EUR_A, "BUY"), _signal(EUR_B, "SELL")],
                            expected_variants=EUR_VARIANTS)
    assert result["status"] == "CONFLICT"
    assert result["selected_signal"] is None
    assert set(result["conflict"]["signals_by_direction"]) == {"LONG", "SHORT"}


def test_pair_backtest_selection_does_not_leak_status_into_trade_row():
    from backtest.free_open_data_variants import select_pair_signals

    candidate = _signal(EUR_A, "LONG")
    candidate.update({
        "entry_reference": 1.1, "stop": 1.09, "target": 1.12,
        "planned_rr": 2.0, "event_time_utc": STAMP,
    })
    selected, audit = select_pair_signals("EURUSD", [candidate])
    assert len(selected) == 1
    assert "status" not in selected[0]
    assert audit[0]["status"] == "SELECTED"


def test_conflict_audit_is_persisted_to_jsonl_and_sqlite(tmp_path, monkeypatch):
    from execution.storage import EventStore

    selection = select_signals(
        [_signal(EUR_A, "BUY"), _signal(EUR_B, "SELL")],
        expected_variants=EUR_VARIANTS,
    )
    assert selection["status"] == "CONFLICT"
    diagnostics = tmp_path / "logs" / "events.jsonl"
    monkeypatch.setattr(demo_runner, "DIAGNOSTICS_PATH", diagnostics)
    monkeypatch.setattr(demo_runner, "STORAGE_LIMIT_BYTES", 1_000_000)
    database = tmp_path / "events.sqlite3"
    store = EventStore(database)
    try:
        demo_runner._record({
            "event": "signal_selection", "pair": "EURUSD", "selection": selection,
        }, store)
    finally:
        store.close()
    jsonl_row = json.loads(diagnostics.read_text().splitlines()[0])
    assert jsonl_row["selection"]["status"] == "CONFLICT"
    assert len(jsonl_row["selection"]["candidate_signal_ids"]) == 2
    import sqlite3
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT status, selected_variant, selected_signal_id, conflict_json, selection_json "
            "FROM signal_selections"
        ).fetchone()
    assert row[0] == "CONFLICT"
    assert row[1] is None and row[2] is None
    assert json.loads(row[3])["type"] == "OPPOSING_VARIANT_DIRECTIONS"
    assert json.loads(row[4])["candidate_signal_ids"] == selection["candidate_signal_ids"]


def test_conflict_remains_in_sqlite_when_jsonl_quota_is_reached(tmp_path, monkeypatch):
    from execution.storage import EventStore
    import sqlite3

    selection = select_signals(
        [_signal(EUR_A, "BUY"), _signal(EUR_B, "SELL")],
        expected_variants=EUR_VARIANTS,
    )
    diagnostics = tmp_path / "logs" / "events.jsonl"
    monkeypatch.setattr(demo_runner, "DIAGNOSTICS_PATH", diagnostics)
    monkeypatch.setattr(demo_runner, "STORAGE_LIMIT_BYTES", 1)
    database = tmp_path / "events.sqlite3"
    store = EventStore(database)
    try:
        demo_runner._record({
            "event": "signal_selection", "pair": "EURUSD", "selection": selection,
        }, store)
    finally:
        store.close()
    assert not diagnostics.exists()
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT status, conflict_json FROM signal_selections"
        ).fetchone()
    assert row[0] == "CONFLICT"
    assert json.loads(row[1])["type"] == "OPPOSING_VARIANT_DIRECTIONS"


def test_variant_scoped_identity_distinguishes_same_pair_and_timestamp():
    first, second = _signal(EUR_A), _signal(EUR_B)
    assert signal_identity(first) != signal_identity(second)
    selected = select_signals([first, second], expected_variants=EUR_VARIANTS)
    assert len(selected["candidate_signal_ids"]) == 2


def test_missing_variant_result_fails_closed_instead_of_picking_first_signal():
    result = select_signals([_signal(EUR_A)], expected_variants=EUR_VARIANTS)
    assert result["status"] == "INCOMPLETE"
    assert result["selected_signal"] is None
    assert result["missing_variants"] == [EUR_B]


def test_unknown_variant_status_fails_closed():
    result = select_signals([
        _signal(EUR_A), {"pair": "EURUSD", "variant": EUR_B, "status": "TIMEOUT"}
    ], expected_variants=EUR_VARIANTS)
    assert result["status"] == "INCOMPLETE"
    assert result["selected_signal"] is None
    assert result["invalid_statuses"] == [{"variant": EUR_B, "status": "TIMEOUT"}]


def test_pair_setup_states_remain_isolated_per_variant():
    states = {"setups": {
        f"EURUSD:{EUR_A}": {"status": "WAITING_FOR_POI_TOUCH", "id": "a"},
        f"EURUSD:{EUR_B}": {"status": "CONFIRMED", "id": "b"},
    }}
    result = demo_runner._variant_setup_states("EURUSD", states)
    assert result[EUR_A]["id"] == "a"
    assert result[EUR_B]["id"] == "b"
    assert result[EUR_A] is not result[EUR_B]


def test_only_selected_signal_is_returned_for_order_execution():
    signal = _signal(EUR_A, "BUY")
    selected = select_signals([signal], expected_variants=(EUR_A,))
    executable = demo_runner._selected_signal_for_execution(selected)
    assert executable is not None
    assert executable["signal_id"] == signal_identity(signal)
    assert executable["entry_price"] == signal["entry_price"]
    assert demo_runner._selected_signal_for_execution({
        "status": "CONFLICT", "selected_signal": None,
    }) is None


def test_demo_runner_passes_only_selected_signal_to_order_process(tmp_path, monkeypatch):
    from types import SimpleNamespace

    candidates = [_signal(EUR_A, "BUY", rr=2), _signal(EUR_B, "BUY", rr=3)]
    selection = select_signals(candidates, expected_variants=EUR_VARIANTS)
    monkeypatch.setattr(demo_runner, "load_config", lambda: {})
    monkeypatch.setattr(demo_runner, "configured_pairs", lambda cfg: ["EURUSD"])
    monkeypatch.setattr(demo_runner, "_scan", lambda pair, setup_states=None: {
        "pair": pair, "variant_results": candidates, "selection": selection,
    })
    monkeypatch.setattr(demo_runner, "require_demo_execution", lambda: None)
    monkeypatch.setattr(demo_runner, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(demo_runner, "DIAGNOSTICS_PATH", tmp_path / "logs" / "events.jsonl")
    monkeypatch.setattr(demo_runner, "DATABASE_PATH", str(tmp_path / "events.db"))
    monkeypatch.setenv("CTRADER_PAIRS", "EURUSD")
    monkeypatch.setenv("CTRADER_DEMO_EXECUTE", "true")
    monkeypatch.setenv("CTRADER_RUN_UNTIL_TRADE", "true")
    monkeypatch.setenv("CTRADER_ORDER_VOLUME_UNITS", "1")
    submitted = {}

    def fake_order_process(command, **kwargs):
        submitted["command"] = command
        submitted["signal"] = kwargs["input"]
        return SimpleNamespace(returncode=0, stdout="ORDER_ACKNOWLEDGED", stderr="")

    monkeypatch.setattr(demo_runner.subprocess, "run", fake_order_process)
    assert demo_runner.main() == 0
    order_signal = json.loads(submitted["signal"])
    assert submitted["command"] == [
        demo_runner.sys.executable, "-m", "execution.demo_order",
    ]
    assert order_signal["variant"] == EUR_B
    assert order_signal["signal_id"] == selection["selected_signal_id"]


def test_pair_order_guard_is_downstream_of_evaluation_of_every_variant(monkeypatch):
    evaluated = []
    shared_snapshot = {"same_market_bars": True}
    snapshot_calls = []

    monkeypatch.setattr(bot_main, "load_config", lambda: {})

    def make_snapshot(pair, cfg, end):
        snapshot_calls.append((pair, cfg, end))
        return shared_snapshot

    monkeypatch.setattr(bot_main, "_market_snapshot", make_snapshot)

    def fake_scan(pair, setup_state=None, variant_name=None, market_snapshot=None):
        evaluated.append((variant_name, market_snapshot))
        return _signal(variant_name, "BUY")

    monkeypatch.setattr(bot_main, "scan", fake_scan)
    batch = bot_main.scan_pair("EURUSD")
    assert len(snapshot_calls) == 1
    assert [name for name, _ in evaluated] == list(variants_for_pair("EURUSD"))
    assert all(snapshot is shared_snapshot for _, snapshot in evaluated)
    assert batch["selection"]["status"] == "SELECTED"
    # The demo runner receives only the selected signal; the pair order guard
    # cannot prevent either strategy preset from generating its candidate.
    assert len(batch["variant_results"]) == 2


def test_scanner_and_backtest_use_shared_variant_factory_and_execution_has_no_strategy_engine():
    from strategy import variants as variant_module
    from backtest import free_open_data_variants as backtest_module
    from backtest import original_variants_7d as original_backtest_module

    assert bot_main.build_variant is variant_module.build_variant
    assert "build_variant" in inspect.getsource(backtest_module.collect_signals)
    assert "build_variant" in inspect.getsource(original_backtest_module.signals)
    assert "select_signals" in inspect.getsource(original_backtest_module.select_pair_candidates)
    assert "select_signals" in inspect.getsource(bot_main.scan_pair)
    assert "Strategy(" not in inspect.getsource(bot_main)
    assert "execution.bot_main" in inspect.getsource(demo_runner._scan)
    assert not hasattr(demo_order, "Strategy")
    assert "Strategy(" not in inspect.getsource(demo_order)
    assert "confluence" not in inspect.getsource(demo_order).lower()


def test_pair_backtest_selects_one_simultaneous_variant_and_logs_conflict():
    from backtest.free_open_data_variants import select_pair_signals

    same_time = [_signal(EUR_A, "LONG", rr=2), _signal(EUR_B, "LONG", rr=3)]
    winners, audit = select_pair_signals("EURUSD", same_time)
    assert len(winners) == 1
    assert winners[0]["variant"] == EUR_B
    assert audit[0]["status"] == "SELECTED"

    conflict, conflict_audit = select_pair_signals(
        "EURUSD", [_signal(EUR_A, "LONG"), _signal(EUR_B, "SHORT")]
    )
    assert conflict == []
    assert conflict_audit[0]["status"] == "CONFLICT"
