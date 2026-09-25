from strategy.engine import Strategy
from strategy.svl import alignment_for_execution, analyze_svl, market_profile


def row(i, o, h, l, c, volume=1):
    return {"time": f"2026-01-01T{i:02d}:00:00Z", "open": o, "high": h, "low": l, "close": c, "volume": volume}


def test_market_profile_exposes_value_levels_and_nodes():
    rows = [row(i, 100, 101, 99, 100, 10 if i < 8 else 1) for i in range(12)]
    profile = market_profile(rows, bins=12)
    assert profile is not None
    assert profile.low == 99
    assert profile.high == 101
    assert profile.val <= profile.poc <= profile.vah
    assert profile.hvn


def test_svl_reports_clear_structure_value_and_liquidity_fields():
    rows = []
    for i in range(40):
        base = 100 + (i // 5) * 0.5
        rows.append(row(i, base, base + 0.2, base - 0.2, base + 0.1))
    context = analyze_svl(rows, swing_length=2)
    payload = context.as_dict()
    assert "structure" in payload
    assert "value" in payload
    assert "liquidity" in payload
    assert payload["value"]["poc"] is not None


def test_alignment_has_h1_context_and_latest_m5_event_fields():
    h1 = [row(i, 100 + i * 0.1, 100.3 + i * 0.1, 99.8 + i * 0.1, 100.1 + i * 0.1) for i in range(30)]
    m5 = [row(i, 100 + i * 0.01, 100.1 + i * 0.01, 99.9 + i * 0.01, 100.02 + i * 0.01) for i in range(30)]
    result = alignment_for_execution(h1, m5, swing_length=2)
    assert result["execution"]["timeframe"] == "M5"
    assert "aligned_for_trade" in result


def test_strategy_keeps_svl_as_auditable_layer_by_default():
    rows = [row(i, 100, 101, 99, 100) for i in range(30)]
    decision = Strategy().evaluate(rows, rows)
    assert decision.status == "NO_TRADE"
    assert decision.reason_codes == ["H1_STRUCTURE_UNCLEAR"]
    assert "svl" in decision.evidence
