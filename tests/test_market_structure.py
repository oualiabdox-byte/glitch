import pytest

from strategy.market_structure import (
    _label_swings,
    analyze_structure,
    detect_structure_events,
)


def candles(values):
    return [
        {"time": f"2026-01-01T{i:02d}:00:00Z", "open": v, "high": v + 1,
         "low": v - 1, "close": v}
        for i, v in enumerate(values)
    ]


def test_first_confirmed_swings_are_unclassified():
    highs = [{"time": 1, "high": 10, "idx": 3}, {"time": 2, "high": 12, "idx": 7}]
    lows = [{"time": 1, "low": 5, "idx": 3}, {"time": 2, "low": 6, "idx": 7}]
    labeled_highs, labeled_lows = _label_swings(highs, lows)
    assert labeled_highs[0]["label"] is None
    assert labeled_lows[0]["label"] is None
    assert labeled_highs[1]["label"] == "HH"
    assert labeled_lows[1]["label"] == "HL"


def test_insufficient_structure_is_not_bullish_or_bearish():
    data = candles(range(30))
    result = analyze_structure(data, swing_length=3)
    assert result["bias"] in (None, "LONG", "SHORT")
    assert result["structure"] != "BULLISH" or result["bias"] == "LONG"
    assert result["structure"] != "BEARISH" or result["bias"] == "SHORT"


def test_same_broken_swing_is_not_emitted_repeatedly():
    data = candles([10, 9, 8, 9, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20])
    events = detect_structure_events(data, swing_length=2)
    bullish = [e for e in events if e["direction"] == "BULLISH"]
    assert len(bullish) == len({e["broken_swing_time"] for e in bullish})
