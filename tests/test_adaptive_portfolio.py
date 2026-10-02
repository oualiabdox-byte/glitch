from allocation.adaptive_portfolio import (
    AllocationConfig,
    Candidate,
    allocate,
    conservative_score,
    default_currency_cluster,
)


def candidate(signal_id, pair, score=0.9, expectancy=0.2, sample=100):
    return Candidate(signal_id, pair, "LONG", score, expectancy, sample)


def test_default_policy_is_quarter_percent_per_trade():
    config = AllocationConfig()
    decisions = allocate([candidate("a", "EURUSD")], config=config)
    assert decisions[0].accepted is True
    assert decisions[0].allocated_risk == 0.0025
    assert config.max_portfolio_risk == 0.01


def test_same_currency_cluster_caps_usd_quoted_pairs():
    config = AllocationConfig(max_currency_cluster_risk=0.005, max_correlated_cluster_risk=0.01)
    decisions = allocate([
        candidate("a", "EURUSD"), candidate("b", "GBPUSD"), candidate("c", "AUDUSD"),
    ], config=config)
    assert [d.accepted for d in decisions] == [True, True, False]
    assert decisions[-1].reason == "currency_cluster_cap"
    assert default_currency_cluster("EURUSD") == default_currency_cluster("GBPUSD")


def test_correlation_cap_rejects_cross_cluster_pair():
    config = AllocationConfig(max_currency_cluster_risk=0.01, max_correlated_cluster_risk=0.0025)
    decisions = allocate(
        [candidate("a", "EURUSD"), candidate("b", "XAUUSD")],
        config=config,
        correlations={("EURUSD", "XAUUSD"): 0.85},
    )
    assert decisions[0].accepted is True
    assert decisions[1].accepted is False
    assert decisions[1].reason == "correlation_cluster_cap"


def test_low_quality_signal_is_rejected_and_ranking_is_deterministic():
    config = AllocationConfig(max_currency_cluster_risk=0.01, max_correlated_cluster_risk=0.01)
    decisions = allocate([
        candidate("low", "EURUSD", score=0.40),
        candidate("high", "USDJPY", score=0.90),
    ], config=config)
    by_id = {d.signal_id: d for d in decisions}
    assert by_id["high"].accepted is True
    assert by_id["low"].reason == "quality_below_floor"
    assert conservative_score(candidate("x", "EURUSD", sample=0), config) < conservative_score(candidate("x", "EURUSD", sample=100), config)


def test_existing_risk_is_counted_before_new_allocations():
    config = AllocationConfig(max_portfolio_risk=0.005, max_currency_cluster_risk=0.01, max_correlated_cluster_risk=0.01)
    existing = [candidate("open", "USDJPY")]
    decisions = allocate([candidate("new", "EURUSD")], config=config,
                         existing=existing, existing_allocations={"open": 0.0025})
    assert decisions[0].accepted is True
    assert decisions[0].portfolio_risk_after == 0.005
    blocked_config = AllocationConfig(max_portfolio_risk=0.004, max_currency_cluster_risk=0.01, max_correlated_cluster_risk=0.01)
    assert allocate([candidate("blocked", "GBPUSD")], config=blocked_config,
                    existing=existing, existing_allocations={"open": 0.0025})[0].reason == "portfolio_risk_cap"
