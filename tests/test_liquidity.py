from strategy import liquidity, market_structure


def candle(t, o, h, l, c):
    return {"time": t, "open": o, "high": h, "low": l, "close": c}


def test_previous_day_levels_use_calendar_days():
    bars = [
        candle("2026-01-01T00:00:00Z", 1.1, 1.11, 1.09, 1.10),
        candle("2026-01-01T04:00:00Z", 1.1, 1.12, 1.08, 1.10),
        candle("2026-01-02T00:00:00Z", 1.11, 1.13, 1.10, 1.12),
        candle("2026-01-02T04:00:00Z", 1.12, 1.14, 1.11, 1.13),
    ]
    high, low = liquidity.previous_day_high_low(bars)
    assert high == 1.12
    assert low == 1.08


def test_eqh_eql_are_clustered_from_confirmed_swings(monkeypatch):
    bars = [candle(str(i), 1.0, 1.0, 0.9, 1.0) for i in range(10)]
    monkeypatch.setattr(
        market_structure,
        "find_swing_highs",
        lambda candles, length=3: [
            {"time": "2", "high": 1.1000, "idx": 2},
            {"time": "6", "high": 1.1001, "idx": 6},
        ],
    )
    monkeypatch.setattr(
        market_structure,
        "find_swing_lows",
        lambda candles, length=3: [
            {"time": "3", "low": 0.9000, "idx": 3},
            {"time": "7", "low": 0.9001, "idx": 7},
        ],
    )
    monkeypatch.setattr(liquidity, "_atr", lambda candles, period=14: 0.001)
    eqh, eql = liquidity.equal_highs_lows(bars, tolerance_atr=0.15)
    assert len(eqh) == 1 and eqh[0]["count"] == 2
    assert len(eql) == 1 and eql[0]["count"] == 2
