"""Causal FVG / order-block / breaker-block context.

These detectors are evidence-only by default. A caller may enable a confluence
gate after a separate ablation; the canonical entry rules remain unchanged.
"""
from __future__ import annotations
from typing import Any
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

def build_poi_confluence(candles: list[Candle], fvg: PointOfInterest, side: Side, low: float, high: float, event_index: int) -> dict[str, Any]:
    order_block=find_order_block(candles, side, event_index, low, high)
    breaker=find_breaker_block(candles, side, event_index, low, high)
    overlaps={"FVG":True,
              "ORDER_BLOCK":bool(order_block and order_block.overlaps(candles[event_index])),
              "BREAKER_BLOCK":bool(breaker and breaker.overlaps(candles[event_index]))}
    fvg_overlap_ob=bool(order_block and order_block.overlaps(candles[fvg.index]))
    fvg_overlap_breaker=bool(breaker and breaker.overlaps(candles[fvg.index]))
    return {"fvg":fvg.as_dict(),
            "order_block":order_block.as_dict() if order_block else None,
            "breaker_block":breaker.as_dict() if breaker else None,
            "overlap_at_event":overlaps,
            "available_count":sum(bool(x) for x in (fvg, order_block, breaker)),
            "confluence_count":1+int(fvg_overlap_ob)+int(fvg_overlap_breaker),
            "fvg_overlap_order_block":fvg_overlap_ob,
            "fvg_overlap_breaker_block":fvg_overlap_breaker}
