from strategy import risk


def test_position_size_uses_tick_value_and_volume_step():
    spec = {
        "tickSize": 0.0001,
        "tickValue": 10.0,
        "lotSize": 100000,
        "minVolume": 1000,
        "maxVolume": 1000000,
        "stepVolume": 1000,
    }
    # 20 pip stop = $200 risk per lot; $100 risk => 0.5 lot.
    units = risk.position_size_from_symbol(
        risk_amount=100.0,
        entry_price=1.1000,
        stop_price=1.0980,
        symbol_spec=spec,
    )
    assert units == 50000.0


def test_position_size_rejects_zero_distance():
    try:
        risk.position_size_from_symbol(
            risk_amount=100.0,
            entry_price=1.1,
            stop_price=1.1,
            symbol_spec={"tickSize": 0.0001, "tickValue": 10, "lotSize": 100000},
        )
    except ValueError:
        return
    assert False


def test_position_size_respects_minimum_volume():
    spec = {
        "tickSize": 0.0001,
        "tickValue": 10.0,
        "lotSize": 100000,
        "minVolume": 10000,
        "maxVolume": 1000000,
        "stepVolume": 10000,
    }
    assert risk.position_size_from_symbol(
        risk_amount=1.0,
        entry_price=1.1000,
        stop_price=1.0900,
        symbol_spec=spec,
    ) == 0.0


def test_currency_exposure_counts_shared_currency():
    assert risk.currency_exposure_allowed(["EURUSD", "GBPUSD"], "AUDUSD", max_shared_currency=2) is False
    assert risk.currency_exposure_allowed(["EURUSD"], "GBPJPY", max_shared_currency=2) is True
