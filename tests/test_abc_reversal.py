import pytest

from strategy import ict_hybrid


def candle(i, close):
    return {
        "time": i,
        "open": close,
        "high": close + 0.5,
        "low": close - 0.5,
        "close": close,
    }


def test_abc_long_requires_fomo_ll_then_break(monkeypatch):
    recent = [candle(i, 100 + i) for i in range(7)]
    recent[6]["close"] = 105.0

    highs = [
        {"idx": 2, "high": 110.0},
        {"idx": 4, "high": 112.0},
    ]
    lows = [
        {"idx": 3, "low": 98.0},
        {"idx": 5, "low": 96.0},
    ]

    monkeypatch.setattr(ict_hybrid.market_structure, "find_swing_highs", lambda candles, length=3: highs)
    monkeypatch.setattr(ict_hybrid.market_structure, "find_swing_lows", lambda candles, length=3: lows)

    result = ict_hybrid._abc_reversal_confirmation(
        recent, sweep_idx=1, side="LONG", swing_length=3
    )

    assert result is not None
    assert result["confirmed"] is True
    assert result["pattern"] == "H_LL_H_FOMO_LL_BREAK"
    assert result["fomo_extreme"]["low"] == 96.0
    assert result["break_level"] == 98.0


def test_abc_short_requires_fomo_hh_then_break(monkeypatch):
    recent = [candle(i, 200 - i) for i in range(7)]
    recent[6]["close"] = 195.0

    lows = [
        {"idx": 2, "low": 190.0},
        {"idx": 4, "low": 188.0},
    ]
    highs = [
        {"idx": 3, "high": 202.0},
        {"idx": 5, "high": 204.0},
    ]

    monkeypatch.setattr(ict_hybrid.market_structure, "find_swing_lows", lambda candles, length=3: lows)
    monkeypatch.setattr(ict_hybrid.market_structure, "find_swing_highs", lambda candles, length=3: highs)

    result = ict_hybrid._abc_reversal_confirmation(
        recent, sweep_idx=1, side="SHORT", swing_length=3
    )

    assert result is not None
    assert result["confirmed"] is True
    assert result["pattern"] == "L_HH_L_FOMO_HH_BREAK"
    assert result["fomo_extreme"]["high"] == 204.0
    assert result["break_level"] == 202.0


def test_abc_does_not_use_current_candle_as_pivot(monkeypatch):
    recent = [candle(i, 100 + i) for i in range(7)]
    seen_lengths = []

    def highs(candles, length=3):
        seen_lengths.append(len(candles))
        return []

    def lows(candles, length=3):
        seen_lengths.append(len(candles))
        return []

    monkeypatch.setattr(ict_hybrid.market_structure, "find_swing_highs", highs)
    monkeypatch.setattr(ict_hybrid.market_structure, "find_swing_lows", lows)

    ict_hybrid._abc_reversal_confirmation(
        recent, sweep_idx=1, side="LONG", swing_length=3
    )

    assert seen_lengths
    assert all(length == len(recent) - 1 for length in seen_lengths)


def test_abc_rejects_missing_fomo_leg(monkeypatch):
    recent = [candle(i, 100 + i) for i in range(7)]
    highs = [
        {"idx": 2, "high": 110.0},
        {"idx": 4, "high": 112.0},
    ]
    lows = [
        {"idx": 3, "low": 98.0},
    ]

    monkeypatch.setattr(ict_hybrid.market_structure, "find_swing_highs", lambda candles, length=3: highs)
    monkeypatch.setattr(ict_hybrid.market_structure, "find_swing_lows", lambda candles, length=3: lows)

    result = ict_hybrid._abc_reversal_confirmation(
        recent, sweep_idx=1, side="LONG", swing_length=3
    )

    assert result is None
