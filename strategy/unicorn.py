"""Optional, explicitly defined breaker/FVG overlap (Unicorn) research filter.

The community terminology is not universal. This module implements one
causal OHLC variant only: the last opposite-close candle before a directional
break is a candidate breaker origin, and a same-direction completed FVG must
overlap it with positive width. It never creates a setup by itself.
"""
from __future__ import annotations

from .multi_timeframe import _atr, _body_metrics, detect_fvg


def find_unicorn_zone(candles: list[dict], side: str, break_idx: int,
                      tick_size: float = 1e-5, max_age: int = 30,
                      min_fvg_width_atr: float = 0.25,
                      displacement_atr: float = 0.50) -> dict | None:
    if side not in {"LONG", "SHORT"} or break_idx < 2 or break_idx >= len(candles):
        return None
    start = max(0, break_idx - min(max_age, 10))
    ob_idx = None
    for i in range(break_idx - 1, start - 1, -1):
        body = candles[i]["close"] - candles[i]["open"]
        if (side == "LONG" and body < 0) or (side == "SHORT" and body > 0):
            ob_idx = i
            break
    if ob_idx is None:
        return None
    atr = _atr(candles, break_idx)
    metrics = _body_metrics(candles[break_idx], atr)
    if metrics["body_atr"] < displacement_atr:
        return None
    fvg = detect_fvg(candles, break_idx, "BULLISH" if side == "LONG" else "BEARISH",
                     min_width_atr=min_fvg_width_atr, tick_size=tick_size)
    if not fvg:
        return None
    ob = {"bottom": candles[ob_idx]["low"], "top": candles[ob_idx]["high"], "idx": ob_idx}
    bottom = max(ob["bottom"], fvg.bottom)
    top = min(ob["top"], fvg.top)
    if top - bottom <= max(2 * tick_size, 0.0):
        return None
    return {"side": side, "ob": ob, "fvg": {"side": fvg.side, "bottom": fvg.bottom, "top": fvg.top, "created_idx": fvg.created_idx}, "overlap": {"bottom": bottom, "top": top}, "break_idx": break_idx}


__all__ = ["find_unicorn_zone"]
