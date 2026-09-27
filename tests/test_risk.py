from execution.risk import calculate_risk_volume, normalize_volume


SPEC = {"minVolume": 1000, "maxVolume": 100000, "stepVolume": 1000}


def test_volume_rounds_down_to_broker_step():
    assert normalize_volume(2501, SPEC, 100000) == 2000


def test_volume_never_exceeds_cap():
    assert normalize_volume(25000, SPEC, 12000) == 12000


def test_risk_sizing_uses_stop_distance_and_preserves_cap():
    decision = calculate_risk_volume(10000, 0.005, 0.001, 1.0, SPEC, 100000)
    assert decision.mode == "risk"
    assert decision.risk_cash == 50
    assert decision.volume_units == 50000
    assert decision.estimated_loss_cash == 50
