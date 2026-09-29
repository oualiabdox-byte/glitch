from strategy.auction_mean_reversion import (
    AuctionConfig,
    confirms_reversal,
    detect_sweep,
    resolve_exit,
)


def test_detects_long_discount_sweep_and_close_back_inside():
    prior = [
        {"open": 96.3, "high": 96.8, "low": 96.2, "close": 96.4}
        for _ in range(12)
    ]
    current = {"open": 96.0, "high": 96.5, "low": 95.9, "close": 96.35}
    setup = detect_sweep(current, prior, range_low=95.0, range_high=105.0)
    assert setup is not None
    assert setup["side"] == "LONG"
    assert setup["liquidity_level"] == 96.2
    assert setup["value_midpoint"] == 100.0


def test_rejects_sweep_outside_value_extreme():
    prior = [
        {"open": 98.0, "high": 98.4, "low": 97.9, "close": 98.1}
        for _ in range(12)
    ]
    current = {"open": 97.7, "high": 98.2, "low": 97.5, "close": 98.05}
    assert detect_sweep(current, prior, range_low=95.0, range_high=105.0) is None


def test_short_reversal_requires_close_beyond_three_bar_pivot():
    prior = [
        {"open": 104.0, "high": 104.2, "low": 103.8, "close": 104.0},
        {"open": 104.0, "high": 104.1, "low": 103.7, "close": 103.9},
        {"open": 103.9, "high": 104.0, "low": 103.6, "close": 103.8},
    ]
    current = {"open": 103.7, "high": 103.8, "low": 103.2, "close": 103.3}
    assert confirms_reversal("SHORT", current, prior)
    not_break = {**current, "close": 103.75}
    assert not confirms_reversal("SHORT", not_break, prior)


def test_resolve_exit_uses_stop_first_when_both_touched():
    both_touched = {"open": 100.0, "high": 102.0, "low": 98.0, "close": 100.5}
    assert resolve_exit("LONG", both_touched, stop=99.0, target=101.0) == (99.0, "stop")
    assert resolve_exit("SHORT", both_touched, stop=101.0, target=99.0) == (101.0, "stop")


def test_config_keeps_strategy_b_independent_and_uses_fixed_research_defaults():
    cfg = AuctionConfig()
    assert cfg.range_lookback_bars == 288
    assert cfg.min_reward_risk == 1.0
    assert cfg.round_turn_cost_pips == 1.5
