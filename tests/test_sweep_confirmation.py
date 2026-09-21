from strategy import ict_strategy


def bar(i, high, low, close):
    return {"time": i, "open": close, "high": high, "low": low, "close": close}


def test_structure_sweep_uses_confirmed_swing(monkeypatch):
    candles = [
        bar(0, 102, 99, 101),
        bar(1, 103, 100, 102),
        bar(2, 104, 98, 103),
        bar(3, 102, 99, 101),
        bar(4, 101, 100, 100.5),
        bar(5, 105, 96, 101),
        bar(6, 103, 99, 102),
        bar(7, 104, 98, 103),
    ]

    swings = [{"idx": 2, "low": 98.0, "time": 2}]
    monkeypatch.setattr(
        ict_strategy.market_structure,
        "find_swing_lows",
        lambda candles, length=3: swings,
    )

    result = ict_strategy._find_recent_sweep(
        candles,
        "LONG",
        lookback=6,
        reference_bars=5,
        mode="structure",
    )

    assert result is not None
    assert result["source"] == "SWING_LOW"
    assert result["level"] == 98.0
    assert result["extreme"] == 96.0


def test_structure_sweep_rejects_without_confirmed_level(monkeypatch):
    candles = [
        bar(0, 102, 99, 101),
        bar(1, 103, 100, 102),
        bar(2, 104, 98, 103),
        bar(3, 105, 97, 104),
        bar(4, 106, 96, 105),
        bar(5, 107, 95, 106),
    ]

    monkeypatch.setattr(
        ict_strategy.market_structure,
        "find_swing_lows",
        lambda candles, length=3: [],
    )

    assert ict_strategy._find_recent_sweep(
        candles,
        "LONG",
        lookback=6,
        reference_bars=5,
        mode="structure",
    ) is None


def test_legacy_sweep_remains_available():
    candles = [
        bar(0, 101, 100, 100.5),
        bar(1, 102, 99, 101),
        bar(2, 103, 98, 102),
        bar(3, 104, 97, 103),
        bar(4, 105, 96, 104),
        bar(5, 106, 94, 105),
        bar(6, 103, 95, 99),
    ]

    result = ict_strategy._find_recent_sweep(
        candles,
        "LONG",
        lookback=6,
        reference_bars=5,
        mode="legacy",
    )

    assert result is not None
    assert result["source"] == "ROLLING_LOW"
