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
        swing_length=3,
        tolerance_atr=0.10,
        valid_window_bars=6,
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
        swing_length=3,
        tolerance_atr=0.10,
        valid_window_bars=6,
    ) is None


def test_sweep_tolerance_is_volatility_normalized(monkeypatch):
    candles = [
        bar(i, 101 + i, 99 - i * 0.01, 100 + i * 0.1)
        for i in range(8)
    ]
    monkeypatch.setattr(
        ict_strategy.market_structure,
        "find_swing_lows",
        lambda candles, length=3: [{"idx": 2, "low": 98.0, "time": 2}],
    )
    monkeypatch.setattr(ict_strategy, "_atr", lambda candles, period=14: 1.0)

    candles[6]["low"] = 97.95
    candles[6]["close"] = 98.2
    assert ict_strategy._find_recent_sweep(
        candles, "LONG", lookback=6,
        swing_length=3, tolerance_atr=0.10, valid_window_bars=2,
    ) is None

    candles[6]["low"] = 97.80
    assert ict_strategy._find_recent_sweep(
        candles, "LONG", lookback=6,
        swing_length=3, tolerance_atr=0.10, valid_window_bars=2,
    ) is not None


def test_stale_sweep_expires_from_validity_window(monkeypatch):
    candles = [
        bar(i, 101 + i, 99 - i * 0.01, 100 + i * 0.1)
        for i in range(10)
    ]
    monkeypatch.setattr(
        ict_strategy.market_structure,
        "find_swing_lows",
        lambda candles, length=3: [{"idx": 1, "low": 98.0, "time": 1}],
    )
    monkeypatch.setattr(ict_strategy, "_atr", lambda candles, period=14: 1.0)
    candles[2]["low"] = 97.0
    candles[2]["close"] = 98.5

    assert ict_strategy._find_recent_sweep(
        candles, "LONG", lookback=12,
        swing_length=3, valid_window_bars=6,
    ) is None
