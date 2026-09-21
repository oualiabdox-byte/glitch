from config.settings import load_config, pairs


def test_config_is_strict_and_has_single_pair_source():
    cfg = load_config()
    assert cfg["backtest"]["mode"] == "strict_ict_smc"
    assert cfg["backtest"]["look_ahead_guard"] is True
    assert pairs(cfg) == ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD"]
