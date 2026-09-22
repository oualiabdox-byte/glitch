from strategy.decision import Decision, evaluate_entry_decision, no_trade


def test_no_trade_always_contains_reason_and_cutoff():
    result = no_trade("TEST_REASON", data_cutoff_utc="2025-01-01T00:00:00Z")
    assert isinstance(result, Decision)
    assert result.status == "NO_TRADE"
    assert result.reason_codes == ("TEST_REASON",)
    assert result.as_dict()["data_cutoff_utc"].endswith("Z")


def test_entry_decision_rejects_insufficient_history_without_none():
    result = evaluate_entry_decision([], [], "GBPUSD", "ict_fvg")
    assert result.status == "NO_TRADE"
    assert result.reason_codes == ("INSUFFICIENT_HISTORY",)
    assert result.setup is None


def test_unknown_mode_with_insufficient_data_is_still_a_decision():
    bars_1h = [{"time": str(i), "open": 1, "high": 2, "low": 0, "close": 1} for i in range(30)]
    bars_4h = [{"time": str(i), "open": 1, "high": 2, "low": 0, "close": 1} for i in range(30)]
    result = evaluate_entry_decision(bars_1h, bars_4h, "GBPUSD", "unknown")
    assert result.status == "NO_TRADE"
    assert result.reason_codes == ("HTF_NO_DIRECTIONAL_BIAS",)
