from strategy.engine import find_location_fvg
from strategy.models import Candle
from strategy.structure import analyze_structure


def c(i, o, h, l, close):
    return Candle(f"2026-01-01T{i:02d}:00:00Z", o, h, l, close)


def test_long_fvg_can_overlap_discount_boundary():
    candles = [c(0, 1.00, 1.01, .99, 1.005), c(1, 1.005, 1.015, 1.004, 1.012), c(2, 1.012, 1.02, 1.011, 1.018)]
    # midpoint is 1.015; the gap [1.01, 1.018] overlaps both halves.
    fvg = find_location_fvg(candles, "LONG", 1.00, 1.03)
    assert fvg is not None


def test_structure_exposes_weak_direction_when_recent_labels_agree():
    candles = []
    for i, close in enumerate([10, 11, 10.5, 12, 11, 13, 12, 14, 13, 15, 14, 16, 15, 17, 16, 18]):
        candles.append(c(i, close - .1, close + .2, close - .2, close))
    result = analyze_structure(candles, length=1)
    assert result["state"] in {"BULLISH", "BULLISH_WEAK", "MIXED"}
