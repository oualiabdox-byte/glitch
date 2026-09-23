import pytest

from strategy.ict_mtf import ICTMTFConfig, fib_ote


def test_long_fib_ote_is_built_from_displacement_leg():
    zone = fib_ote(100.0, 110.0, "LONG")
    assert zone.equilibrium == pytest.approx(105.0)
    assert zone.ote_low == pytest.approx(102.14)
    assert zone.ote_high == pytest.approx(103.82)
    assert zone.contains(103.0)
    assert not zone.contains(106.0)


def test_short_fib_ote_contains_retracement_price():
    zone = fib_ote(110.0, 100.0, "SHORT")
    assert zone.equilibrium == pytest.approx(105.0)
    assert zone.ote_low == pytest.approx(106.18)
    assert zone.ote_high == pytest.approx(107.86)
    assert zone.contains(107.0)
    assert not zone.contains(103.0)


def test_invalid_fib_order_is_rejected():
    with pytest.raises(ValueError):
        ICTMTFConfig(fib_equilibrium=0.80, fib_ote_low=0.618, fib_ote_high=0.786).validate()


def test_default_model_is_strict_about_weak_daily_bias():
    assert ICTMTFConfig().allow_weak_daily is False
