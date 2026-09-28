"""Causal higher-timeframe context for SMC/ICT research.

This module only consumes completed candles supplied by the caller. It does not
create entries or reject signals; callers can use the resulting bias and draw
as evidence or as an explicitly configured gate in later ablations.
"""
from __future__ import annotations
from typing import Any
from .models import Candle
from .structure import analyze_structure

def _structure(rows: list[dict[str, Any]] | None, swing_length: int) -> dict[str, Any]:
    candles=[Candle.from_dict(row) for row in (rows or [])]
    if len(candles) < max(20, swing_length*4+4):
        return {"state":"INSUFFICIENT_HISTORY","side":None,"events":[],"external_high_swing":None,"external_low_swing":None}
    return analyze_structure(candles, swing_length)

def _draw_for_side(structures: dict[str, dict[str, Any]], side: str | None, price: float | None) -> dict[str, Any]:
    if side not in {"LONG","SHORT"} or price is None:
        return {"side":side,"type":"UNKNOWN","price":None,"source":None}
    candidates=[]
    for timeframe,structure in structures.items():
        swing=structure.get("external_high_swing") if side=="LONG" else structure.get("external_low_swing")
        if not swing: continue
        level=float(swing.get("price"))
        if (side=="LONG" and level>price) or (side=="SHORT" and level<price):
            distance=abs(level-price)
            candidates.append((distance,timeframe,level,swing))
    if not candidates:
        return {"side":side,"type":"NOT_FOUND","price":None,"source":None}
    _, timeframe, level, swing=min(candidates,key=lambda x:(x[0],x[1]))
    return {"side":side,"type":"EXTERNAL_LIQUIDITY","price":level,"source":timeframe,"swing":swing}

def build_higher_timeframe_context(
    h4_rows: list[dict[str, Any]] | None,
    d1_rows: list[dict[str, Any]] | None,
    *, side: str | None = None,
    current_price: float | None = None,
    swing_length: int = 2,
) -> dict[str, Any]:
    structures={"H4":_structure(h4_rows,swing_length),"D1":_structure(d1_rows,swing_length)}
    d1_side=structures["D1"].get("side"); h4_side=structures["H4"].get("side")
    observed_side=side if side in {"LONG","SHORT"} else h4_side or d1_side
    agreement=bool(d1_side and h4_side and d1_side==h4_side)
    return {"timeframes":{"context":"H1","higher":["H4","D1"]},
            "d1":{"bias":d1_side,"state":structures["D1"].get("state"),"external_high":structures["D1"].get("external_high_swing"),"external_low":structures["D1"].get("external_low_swing")},
            "h4":{"bias":h4_side,"state":structures["H4"].get("state"),"external_high":structures["H4"].get("external_high_swing"),"external_low":structures["H4"].get("external_low_swing")},
            "bias":observed_side,"bias_agreement":agreement,
            "liquidity_draw":_draw_for_side(structures,observed_side,current_price)}
