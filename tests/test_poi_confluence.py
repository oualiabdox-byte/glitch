from strategy.models import Candle, PointOfInterest
from strategy.poi_confluence import build_poi_confluence


def _candles(extra=None):
    rows = [
        Candle("2026-01-01T00:00:00+00:00", 10.0, 10.2, 9.0, 9.5),
        Candle("2026-01-01T01:00:00+00:00", 9.6, 12.2, 9.4, 12.0),
        Candle("2026-01-01T02:00:00+00:00", 12.0, 12.3, 11.6, 12.1),
    ]
    return rows + (extra or [])


def test_ob_quality_is_causal_at_structure_event():
    fvg = PointOfInterest("FVG", "LONG", 10.0, 10.5, 1, "2026-01-01T01:00:00+00:00")
    before = build_poi_confluence(_candles(), fvg, "LONG", 9.0, 12.5, event_index=1)
    after = build_poi_confluence(
        _candles([Candle("2026-01-01T03:00:00+00:00", 12.1, 20.0, 8.0, 8.5)]),
        fvg, "LONG", 9.0, 12.5, event_index=1,
    )
    assert before["poi_quality_score"] == after["poi_quality_score"]
    assert before["order_block_quality"] == after["order_block_quality"]
    assert before["breaker_block_quality"] == after["breaker_block_quality"]


def test_breaker_quality_records_reclaim_and_impulse():
    fvg = PointOfInterest("FVG", "LONG", 10.0, 10.5, 1, "2026-01-01T01:00:00+00:00")
    result = build_poi_confluence(_candles(), fvg, "LONG", 9.0, 12.5, event_index=1)
    assert result["breaker_block"] is not None
    assert result["breaker_block_quality"]["reclaimed"] is True
    assert result["breaker_block_quality"]["impulse_ratio"] > 0
