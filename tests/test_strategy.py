from strategy import Strategy
from strategy.engine import find_latest_bos, find_swings
from strategy.models import Candle


def c(i, o, h, l, cl):
    return {"time": f"2026-01-01T{i:02d}:00:00Z", "open": o, "high": h, "low": l, "close": cl}


def test_wick_does_not_confirm_bos():
    candles = [Candle.from_dict(c(i, 10, 11, 9, 10)) for i in range(20)]
    candles[5] = Candle.from_dict(c(5, 10, 12, 9, 10.5))
    candles[6] = Candle.from_dict(c(6, 10.5, 13, 10, 10.7))
    swings = find_swings(candles)
    assert find_latest_bos(candles, swings, "LONG") is None


def test_strategy_returns_auditable_reason_when_history_is_short():
    decision = Strategy().evaluate([c(i, 1, 2, 0.5, 1.5) for i in range(5)], [c(i, 1, 2, 0.5, 1.5) for i in range(5)])
    assert decision.status == "NO_TRADE"
    assert decision.reason_codes == ["INSUFFICIENT_HISTORY"]
    assert decision.evidence["timeframes"] == {"context": "1H", "execution": "M5"}


def test_structure_engine_does_not_force_direction_in_a_range():
    h1 = [c(i, 10, 11, 9, 10) for i in range(30)]
    m5 = [c(i, 10, 11, 9, 10) for i in range(30)]
    decision = Strategy().evaluate(h1, m5)
    assert decision.status == "NO_TRADE"
    assert decision.reason_codes == ["H1_STRUCTURE_UNCLEAR"]
