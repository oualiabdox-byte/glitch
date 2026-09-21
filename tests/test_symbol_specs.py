from data.ctrader import normalize_symbol_spec


class Symbol:
    symbolId = 42
    digits = 5
    pipPosition = 4
    lotSize = 10000000
    minVolume = 100000
    maxVolume = 100000000
    stepVolume = 100000


def test_ctrader_volume_fields_are_converted_from_cents():
    spec = normalize_symbol_spec(Symbol())
    assert spec["lotSize"] == 100000.0
    assert spec["minVolume"] == 1000.0
    assert spec["maxVolume"] == 1000000.0
    assert spec["stepVolume"] == 1000.0
