"""Causal FVG / order-block / breaker-block context.

These detectors are evidence-only by default. A caller may enable a confluence
gate after a separate ablation; the canonical entry rules remain unchanged.
"""
from __future__ import annotations
from typing import Any
from statistics import median
from .models import Candle, PointOfInterest, Side

def _inside(poi: PointOfInterest, low: float, high: float) -> bool:
    return poi.top >= low and poi.bottom <= high

def find_order_block(candles: list[Candle], side: Side, event_index: int, low: float, high: float) -> PointOfInterest | None:
    """Last opposite-body candle before the directional event, if in range."""
    for index in range(min(event_index - 1, len(candles) - 1), -1, -1):
        candle=candles[index]
        bullish=candle.close > candle.open
        bearish=candle.close < candle.open
        valid=(side == "LONG" and bearish) or (side == "SHORT" and bullish)
        if valid:
            poi=PointOfInterest("ORDER_BLOCK", side, candle.low, candle.high, index, candle.time)
            return poi if _inside(poi, low, high) else None
    return None

def find_breaker_block(candles: list[Candle], side: Side, event_index: int, low: float, high: float) -> PointOfInterest | None:
    """A failed opposite candle zone reclaimed by the directional event."""
    block=find_order_block(candles, side, event_index, low, high)
    if block is None: return None
    after=candles[block.index + 1:event_index + 1]
    reclaimed=(side == "LONG" and any(c.close > block.top for c in after)) or (side == "SHORT" and any(c.close < block.bottom for c in after))
    if not reclaimed: return None
    return PointOfInterest("BREAKER_BLOCK", side, block.bottom, block.top, block.index, block.time)

def _atr(candles: list[Candle], index: int, period: int = 14) -> float:
    start = max(0, index - period + 1)
    ranges = []
    for i in range(start, index + 1):
        previous = candles[i - 1].close if i else candles[i].close
        ranges.append(max(candles[i].high - candles[i].low,
                          abs(candles[i].high - previous),
                          abs(candles[i].low - previous)))
    return median(ranges) if ranges else 0.0

def _block_quality(candles: list[Candle], block: PointOfInterest | None,
                   event_index: int, side: Side) -> dict[str, Any]:
    """Score only evidence available through the structure event.

    This deliberately does not use candles after ``event_index``. It measures
    whether the candidate produced a decisive reclaim/impulse and whether its
    opposing edge was already violated before the event.
    """
    if block is None or block.index >= event_index:
        return {"available": False, "score": 0.0, "impulse_ratio": 0.0,
                "reclaimed": False, "fresh": False}
    impulse_index = None
    invalidated = False
    for index in range(block.index + 1, event_index + 1):
        candle = candles[index]
        reclaimed = (candle.close > block.top if side == "LONG"
                     else candle.close < block.bottom)
        violated = (candle.close < block.bottom if side == "LONG"
                    else candle.close > block.top)
        if reclaimed and impulse_index is None:
            impulse_index = index
        if violated:
            invalidated = True
    ratio = 0.0
    if impulse_index is not None:
        atr = _atr(candles, impulse_index)
        body = abs(candles[impulse_index].close - candles[impulse_index].open)
        ratio = body / atr if atr > 0 else 0.0
    impulse_score = min(1.0, ratio / 1.0)
    fresh_score = 0.0 if invalidated else 1.0
    score = 0.55 * impulse_score + 0.45 * fresh_score
    return {"available": True, "score": score, "impulse_ratio": ratio,
            "reclaimed": impulse_index is not None, "fresh": not invalidated,
            "impulse_index": impulse_index}

def build_poi_confluence(candles: list[Candle], fvg: PointOfInterest, side: Side, low: float, high: float, event_index: int) -> dict[str, Any]:
    order_block=find_order_block(candles, side, event_index, low, high)
    breaker=find_breaker_block(candles, side, event_index, low, high)
    overlaps={"FVG":True,
              "ORDER_BLOCK":bool(order_block and order_block.overlaps(candles[event_index])),
              "BREAKER_BLOCK":bool(breaker and breaker.overlaps(candles[event_index]))}
    fvg_overlap_ob=bool(order_block and order_block.overlaps(candles[fvg.index]))
    fvg_overlap_breaker=bool(breaker and breaker.overlaps(candles[fvg.index]))
    ob_quality=_block_quality(candles, order_block, event_index, side)
    breaker_quality=_block_quality(candles, breaker, event_index, side)
    poi_quality_score=(0.50 * min(1.0, (1 + int(fvg_overlap_ob) + int(fvg_overlap_breaker)) / 3)
                       + 0.30 * max(ob_quality["score"], breaker_quality["score"])
                       + 0.20 * int(bool(breaker)))
    return {"fvg":fvg.as_dict(),
            "order_block":order_block.as_dict() if order_block else None,
            "breaker_block":breaker.as_dict() if breaker else None,
            "overlap_at_event":overlaps,
            "available_count":sum(bool(x) for x in (fvg, order_block, breaker)),
            "confluence_count":1+int(fvg_overlap_ob)+int(fvg_overlap_breaker),
            "fvg_overlap_order_block":fvg_overlap_ob,
            "fvg_overlap_breaker_block":fvg_overlap_breaker,
            "order_block_quality": ob_quality,
            "breaker_block_quality": breaker_quality,
            "poi_quality_score": poi_quality_score}
