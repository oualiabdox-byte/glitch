"""Native Structure-Value-Liquidity analysis.

Structure is consumed from the same causal engine used by strategy decisions;
this module only adds value-profile and liquidity context.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .models import Candle, Side
from .structure import analyze_structure, get_m5_execution_confirmation


@dataclass(frozen=True)
class MarketProfile:
    low: float
    high: float
    vah: float
    poc: float
    val: float
    hvn: tuple[float, ...]
    lvn: tuple[float, ...]
    bins: int


@dataclass(frozen=True)
class LiquiditySnapshot:
    equal_highs: tuple[float, ...]
    equal_lows: tuple[float, ...]
    swept_high: float | None
    swept_low: float | None


@dataclass(frozen=True)
class SVLContext:
    side: Side | None
    structure_state: str
    value_location: Literal["DISCOUNT", "PREMIUM", "EQUILIBRIUM", "UNKNOWN"]
    aligned: bool
    structure: dict[str, Any]
    value: MarketProfile | None
    liquidity: LiquiditySnapshot
    alignment_reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        def profile_dict(profile: MarketProfile | None):
            if profile is None:
                return None
            return {"low": profile.low, "high": profile.high, "vah": profile.vah,
                    "poc": profile.poc, "val": profile.val,
                    "hvn": list(profile.hvn), "lvn": list(profile.lvn), "bins": profile.bins}
        return {
            "side": self.side, "structure_state": self.structure_state,
            "value_location": self.value_location, "aligned": self.aligned,
            "alignment_reasons": list(self.alignment_reasons), "structure": self.structure,
            "value": profile_dict(self.value),
            "liquidity": {"equal_highs": list(self.liquidity.equal_highs),
                          "equal_lows": list(self.liquidity.equal_lows),
                          "swept_high": self.liquidity.swept_high,
                          "swept_low": self.liquidity.swept_low},
        }


def _price_bin(price: float, low: float, high: float, bins: int) -> int:
    if high <= low:
        return 0
    return max(0, min(bins - 1, int((price - low) / (high - low) * bins)))


def market_profile(rows: list[dict[str, Any]], bins: int = 24, value_area: float = 0.70) -> MarketProfile | None:
    """Build a deterministic OHLC tick-volume profile (not centralized volume)."""
    candles = [Candle.from_dict(row) for row in rows]
    if not candles:
        return None
    bins = max(4, int(bins))
    low = min(c.low for c in candles)
    high = max(c.high for c in candles)
    if high <= low:
        return MarketProfile(low, high, low, low, low, (low,), (low,), bins)
    weights = [0.0] * bins
    for row, candle in zip(rows, candles):
        volume = float(row.get("volume", 1.0) or 1.0)
        weights[_price_bin((candle.high + candle.low + candle.close) / 3, low, high, bins)] += volume
    poc_i = max(range(bins), key=lambda i: weights[i])
    target = sum(weights) * max(0.5, min(0.95, float(value_area)))
    selected = {poc_i}
    covered = weights[poc_i]
    while covered < target and len(selected) < bins:
        candidates = [i for i in (min(selected) - 1, max(selected) + 1)
                      if 0 <= i < bins and i not in selected]
        if not candidates:
            break
        chosen = max(candidates, key=lambda i: weights[i])
        selected.add(chosen)
        covered += weights[chosen]
    def level(i: int) -> float:
        return low + (i + 0.5) * (high - low) / bins
    vah_i, val_i = max(selected), min(selected)
    positive = [i for i, weight in enumerate(weights) if weight > 0] or [poc_i]
    peak_cutoff = max(weights) * 0.70
    hvn = tuple(level(i) for i in positive if weights[i] >= peak_cutoff)
    lvn = tuple(level(i) for i in positive if weights[i] <= max(weights) * 0.25)
    return MarketProfile(low, high, level(vah_i), level(poc_i), level(val_i), hvn, lvn, bins)


def _equal_levels(values: list[float], tolerance: float) -> tuple[float, ...]:
    levels: list[float] = []
    for value in values:
        if any(abs(value - existing) <= tolerance for existing in levels):
            continue
        matches = [other for other in values if abs(value - other) <= tolerance]
        if len(matches) >= 2:
            levels.append(sum(matches) / len(matches))
    return tuple(levels)


def liquidity_snapshot(candles: list[Candle], structure: dict[str, Any], tolerance_pct: float = 0.001) -> LiquiditySnapshot:
    highs = [float(item["price"]) for item in structure.get("highs", [])]
    lows = [float(item["price"]) for item in structure.get("lows", [])]
    reference = max((c.high for c in candles), default=0.0)
    tolerance = max(reference * float(tolerance_pct), 1e-10)
    eq_highs = _equal_levels(highs, tolerance)
    eq_lows = _equal_levels(lows, tolerance)
    swept_high = swept_low = None
    for level in eq_highs:
        for candle in candles:
            if candle.high > level + tolerance and candle.close < level:
                swept_high = level
    for level in eq_lows:
        for candle in candles:
            if candle.low < level - tolerance and candle.close > level:
                swept_low = level
    return LiquiditySnapshot(eq_highs, eq_lows, swept_high, swept_low)


def _structure_view(structure: dict[str, Any]) -> dict[str, Any]:
    return {key: structure.get(key) for key in (
        "side", "state", "protected_swing", "external_high", "external_low",
        "external_high_index", "external_low_index", "events", "last_event",
        "equilibrium", "swing_length", "closed_candle_count")}


def analyze_svl(rows: list[dict[str, Any]], swing_length: int = 3, profile_bins: int = 24,
                equal_tolerance_pct: float = 0.001,
                structure: dict[str, Any] | None = None) -> SVLContext:
    candles = [Candle.from_dict(row) for row in rows]
    canonical = structure if structure is not None else analyze_structure(candles, swing_length)
    profile = market_profile(rows, profile_bins)
    liquidity = liquidity_snapshot(candles, canonical, equal_tolerance_pct)
    side = canonical.get("side")
    current = candles[-1].close if candles else None
    if profile is None or current is None:
        location = "UNKNOWN"
    elif current < profile.poc:
        location = "DISCOUNT"
    elif current > profile.poc:
        location = "PREMIUM"
    else:
        location = "EQUILIBRIUM"
    reasons: list[str] = []
    if side is None:
        reasons.append("STRUCTURE_UNCLEAR")
    elif side == "LONG" and location != "DISCOUNT":
        reasons.append("LONG_NOT_IN_DISCOUNT")
    elif side == "SHORT" and location != "PREMIUM":
        reasons.append("SHORT_NOT_IN_PREMIUM")
    if side == "LONG" and liquidity.swept_low is None:
        reasons.append("BULLISH_LIQUIDITY_SWEEP_NOT_CONFIRMED")
    if side == "SHORT" and liquidity.swept_high is None:
        reasons.append("BEARISH_LIQUIDITY_SWEEP_NOT_CONFIRMED")
    return SVLContext(side, canonical.get("state", "UNDEFINED"), location, not reasons,
                      _structure_view(canonical), profile, liquidity, tuple(reasons))


def alignment_for_execution(h1_rows: list[dict[str, Any]], m5_rows: list[dict[str, Any]],
                            swing_length: int = 3, profile_bins: int = 24,
                            equal_tolerance_pct: float = 0.001,
                            h1_structure: dict[str, Any] | None = None,
                            m5_structure: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return canonical H1 structure plus same-stream, newest-first M5 checks."""
    h1_candles = [Candle.from_dict(row) for row in h1_rows]
    h1_structure = h1_structure or analyze_structure(h1_candles, swing_length)
    h1 = analyze_svl(h1_rows, swing_length, profile_bins, equal_tolerance_pct,
                     structure=h1_structure)
    m5_candles = [Candle.from_dict(row) for row in m5_rows]
    m5_structure = m5_structure or analyze_structure(m5_candles, swing_length)
    confirmation = get_m5_execution_confirmation(
        m5_candles, h1.side, swing_length, structure=m5_structure,
    )
    execution_reason_codes = list(confirmation.reason_codes)
    if not h1.aligned:
        execution_reason_codes.extend(h1.alignment_reasons)
    output = h1.as_dict()
    output["execution"] = {"timeframe": "M5", **confirmation.as_dict(),
                           "reason_codes": execution_reason_codes}
    output["aligned_for_trade"] = not execution_reason_codes
    return output
