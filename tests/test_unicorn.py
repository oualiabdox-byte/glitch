from strategy.unicorn import find_unicorn_zone


def bar(o, h, l, c, i):
    return {"time": str(i), "open": o, "high": h, "low": l, "close": c}


def test_unicorn_requires_positive_breaker_fvg_overlap():
    candles = [
        bar(100, 102, 98, 99, 0),  # bearish breaker origin
        bar(99, 101, 98.5, 100.5, 1),
        bar(100.5, 103, 101, 102.5, 2),
        bar(101.5, 104, 101.5, 103.8, 3),
    ]
    zone = find_unicorn_zone(candles, "LONG", 3, tick_size=0.01, min_fvg_width_atr=0.0)
    assert zone is not None
    assert zone["overlap"]["top"] > zone["overlap"]["bottom"]


def test_unicorn_rejects_wrong_direction():
    candles = [bar(100, 101, 99, 100, i) for i in range(4)]
    assert find_unicorn_zone(candles, "SHORT", 3) is None
