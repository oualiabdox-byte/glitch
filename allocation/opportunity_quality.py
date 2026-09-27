"""Causal quality features for already-valid canonical opportunities.

This module never manufactures or rejects strategy signals. It scores only data
available at the signal close, using existing strategy evidence plus prior M5
bars. It is research-only until walk-forward validation supports demo use.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite
from statistics import median
from typing import Any
import pandas as pd

def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))

def _norm(value: float, low: float, high: float) -> float:
    return _clip((value-low)/(high-low)) if high > low else 0.5

def _prior(frame: pd.DataFrame, timestamp: str, lookback: int = 48) -> pd.DataFrame:
    ts = pd.Timestamp(timestamp)
    if ts.tzinfo is None: ts = ts.tz_localize("UTC")
    else: ts = ts.tz_convert("UTC")
    return frame.loc[frame.index <= ts].tail(lookback)

def regime_features(frame: pd.DataFrame, timestamp: str, side: str, lookback: int = 48) -> dict[str, Any]:
    bars = _prior(frame, timestamp, lookback)
    if len(bars) < 20:
        return {"state":"INSUFFICIENT_HISTORY","score":0.5,"efficiency":0.0,"range_ratio":1.0,"volume_ratio":1.0}
    close = bars["close"].astype(float)
    ranges = (bars["high"]-bars["low"]).astype(float)
    bodies = (bars["close"]-bars["open"]).abs().astype(float)
    efficiency = abs(float(close.iloc[-1]-close.iloc[0])) / max(float(close.diff().abs().sum()), 1e-12)
    range_ratio = float(ranges.tail(12).median()) / max(float(ranges.iloc[:-12].median()), 1e-12)
    volume_ratio = float(bars["volume"].tail(12).median()) / max(float(bars["volume"].iloc[:-12].median()), 1e-12)
    trend = 1.0 if (close.iloc[-1] >= close.iloc[0]) == (str(side).upper()=="LONG") else 0.0
    expansion = _norm(range_ratio, 0.75, 1.35)
    contraction = 1.0-expansion
    trend_strength = _clip(0.5*efficiency + 0.5*trend)
    if trend_strength >= 0.62 and expansion >= 0.5: state="TREND_EXPANSION"
    elif trend_strength >= 0.62: state="TREND_CONTRACTION"
    elif expansion >= 0.5: state="RANGE_EXPANSION"
    elif contraction >= 0.65: state="RANGE_CONTRACTION"
    else: state="TRANSITION"
    score=_clip(0.55*trend_strength + 0.25*expansion + 0.20*_norm(volume_ratio,0.7,1.4))
    return {"state":state,"score":score,"efficiency":efficiency,"range_ratio":range_ratio,"volume_ratio":volume_ratio,"trend_alignment":trend}

def liquidity_quality(signal: dict[str, Any]) -> dict[str, Any]:
    ev=signal.get("evidence") or {}; side=str(signal.get("side",""))
    structure=ev.get("h1_structure") or {}; sweep=(ev.get("m5_liquidity") or {}).get("selected_sweep") or {}
    disp=ev.get("displacement") or {}; conf=ev.get("m5_confirmation") or {}
    rr=float(signal.get("planned_rr") or 0.0)
    alignment=1.0 if structure.get("side")==side else 0.0
    sweep_score=1.0 if sweep else 0.0
    displacement=_norm(float(disp.get("displacement_ratio") or 0.0),0.75,1.75)
    confirmation=1.0 if (conf.get("valid") and conf.get("latest_event_type") in {"BOS","CHOCH"}) else 0.5
    target_score=_norm(rr,0.75,3.0)
    score=_clip(0.20*alignment+0.20*sweep_score+0.25*displacement+0.20*confirmation+0.15*target_score)
    return {"score":score,"alignment":alignment,"sweep":sweep_score,"displacement":displacement,"confirmation":confirmation,"target_rr":target_score}

def score_opportunity(signal: dict[str, Any], frame: pd.DataFrame) -> dict[str, Any]:
    regime=regime_features(frame, signal["signal_close_utc"], signal["side"])
    liquidity=liquidity_quality(signal)
    final=_clip(0.60*liquidity["score"]+0.40*regime["score"])
    return {"regime":regime,"liquidity":liquidity,"quality_score":final}
