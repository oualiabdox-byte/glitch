from strategy import ict_hybrid


def candle(i, close, high=None, low=None):
    return {
        "time": i,
        "open": close,
        "high": high if high is not None else close + 0.5,
        "low": low if low is not None else close - 0.5,
        "close": close,
    }


def test_abc_long_is_tied_to_sweep(monkeypatch):
    recent = [candle(i, 100 + i) for i in range(10)]
    recent[9]["close"] = 102.5

    highs = [{"idx": 2, "high": 110.0}]
    lows_after_break = [{"idx": 2, "low": 97.0}]

    def swing_highs(candles, length=3):
        return highs if len(candles) <= 4 else []

    def swing_lows(candles, length=3):
        return lows_after_break

    monkeypatch.setattr(ict_hybrid.market_structure, "find_swing_highs", swing_highs)
    monkeypatch.setattr(ict_hybrid.market_structure, "find_swing_lows", swing_lows)

    for i in range(4, 8):
        recent[i]["close"] = 111.0
    recent[8]["low"] = 96.0

    result = ict_hybrid._abc_reversal_confirmation(
        recent,
        sweep_idx=3,
        side="LONG",
        sweep={"time": 3, "level": 98.0, "extreme": 98.0},
        swing_length=3,
    )

    assert result is not None
    assert result["confirmed"] is True
    assert result["break_level"] == 98.0
    assert result["fomo_extreme"]["low"] == 97.0


def test_abc_short_is_tied_to_sweep(monkeypatch):
    recent = [candle(i, 200 - i) for i in range(10)]
    recent[9]["close"] = 197.5

    lows = [{"idx": 2, "low": 190.0}]
    highs_after_break = [{"idx": 2, "high": 204.0}]

    monkeypatch.setattr(
        ict_hybrid.market_structure,
        "find_swing_lows",
        lambda candles, length=3: lows if len(candles) <= 4 else [],
    )
    monkeypatch.setattr(
        ict_hybrid.market_structure,
        "find_swing_highs",
        lambda candles, length=3: highs_after_break,
    )

    for i in range(4, 8):
        recent[i]["close"] = 189.0
    recent[8]["high"] = 205.0

    result = ict_hybrid._abc_reversal_confirmation(
        recent,
        sweep_idx=3,
        side="SHORT",
        sweep={"time": 3, "level": 202.0, "extreme": 202.0},
        swing_length=3,
    )

    assert result is not None
    assert result["confirmed"] is True
    assert result["break_level"] == 202.0
    assert result["fomo_extreme"]["high"] == 204.0


def test_abc_rejects_without_fomo(monkeypatch):
    recent = [candle(i, 100 + i) for i in range(10)]
    recent[-1]["close"] = 101.0

    monkeypatch.setattr(
        ict_hybrid.market_structure,
        "find_swing_highs",
        lambda candles, length=3: [{"idx": 2, "high": 110.0}],
    )
    monkeypatch.setattr(
        ict_hybrid.market_structure,
        "find_swing_lows",
        lambda candles, length=3: [],
    )

    for i in range(4, 9):
        recent[i]["close"] = 111.0

    result = ict_hybrid._abc_reversal_confirmation(
        recent,
        sweep_idx=3,
        side="LONG",
        sweep={"time": 3, "level": 98.0, "extreme": 98.0},
        swing_length=3,
    )

    assert result is None


def test_abc_does_not_use_current_candle_as_pivot(monkeypatch):
    recent = [candle(i, 100 + i) for i in range(8)]
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
        recent,
        sweep_idx=3,
        side="LONG",
        sweep={"time": 3, "level": 98.0, "extreme": 98.0},
        swing_length=3,
    )

    assert seen_lengths
    assert max(seen_lengths) <= len(recent) - 1
