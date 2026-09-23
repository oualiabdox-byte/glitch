from strategy.irl_erl_retest import IRLERLConfig, rejection_reasons_irl_erl


def bar(o, h, l, c, i):
    return {"time": str(i), "open": o, "high": h, "low": l, "close": c}


def test_irl_erl_model_rejects_without_daily_bias():
    d1 = [bar(10, 12, 8, 10, 0), bar(10, 11, 9, 10, 1)]
    assert rejection_reasons_irl_erl(d1, [], []) == ["D1_NO_DIRECTIONAL_BIAS"]


def test_irl_erl_config_keeps_external_sweep_and_half_close_explicit():
    cfg = IRLERLConfig()
    cfg.validate()
    assert cfg.fib_half == 0.50
    assert cfg.h1_external_lookback > 0
    assert cfg.allow_weak_daily is False
