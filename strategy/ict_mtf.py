"""Strict, causal 1D -> 1H POI -> 5M ICT/SMC research model.

This module extends the existing engine; it does not replace it or touch broker
execution. It deliberately favors NO_TRADE. All inputs are closed-bar prefixes
and all pivots require right-side confirmation. The terminology is represented
by explicit OHLC rules so parameters can be backtested.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .multi_timeframe import (
    FVG,
    _atr,
    _body_metrics,
    _displacement_qualified,
    _alternating,
    confirmed_pivots,
    daily_bias,
    detect_fvg,
    liquidity_pools,
)


@dataclass(frozen=True)
class ICTMTFConfig:
    # H1 POI / structure
    h1_swing_length: int = 5
    h1_fvg_min_atr: float = 0.10
    h1_liquidity_lookback: int = 24
    h1_poi_max_age: int = 48
    h1_poi_tolerance_atr: float = 0.25
    # M5 confirmation
    m5_swing_length: int = 3
    m5_sweep_lookback: int = 18
    m5_sweep_buffer_atr: float = 0.10
    m5_bos_buffer_atr: float = 0.10
    m5_displacement_body_atr: float = 0.75
    m5_displacement_body_range: float = 0.50
    m5_two_bar_displacement_atr: float = 1.00
    # Fib / entry
    fib_equilibrium: float = 0.50
    fib_ote_low: float = 0.618
    fib_ote_high: float = 0.786
    entry_expiry_bars: int = 8
    m5_fvg_min_atr: float = 0.05
    require_m5_confluence: bool = False
    # Strictness / risk
    allow_weak_daily: bool = False
    weak_daily_risk_multiplier: float = 0.50

    def validate(self) -> None:
        if self.h1_swing_length < 2 or self.m5_swing_length < 2:
            raise ValueError("swing lengths must be >= 2")
        if not 0 < self.fib_equilibrium < self.fib_ote_low < self.fib_ote_high < 1:
            raise ValueError("fib levels must satisfy 0 < equilibrium < OTE low < OTE high < 1")
        if self.entry_expiry_bars < 1 or self.h1_poi_max_age < 1:
            raise ValueError("expiry windows must be positive")
        if self.weak_daily_risk_multiplier <= 0 or self.weak_daily_risk_multiplier > 1:
            raise ValueError("weak daily risk multiplier must be in (0, 1]")


@dataclass(frozen=True)
class H1POI:
    side: str
    bottom: float
    top: float
    created_idx: int
    sweep_idx: int
    fvg: dict[str, Any]
    premium_discount: str
    poi_type: str = "H1_FVG_AFTER_LIQUIDITY_SWEEP"


@dataclass(frozen=True)
class FibZone:
    side: str
    origin: float
    extreme: float
    equilibrium: float
    ote_low: float
    ote_high: float

    def contains(self, price: float) -> bool:
        return min(self.ote_low, self.ote_high) <= price <= max(self.ote_low, self.ote_high)


def _direction(side: str) -> int:
    if side == "LONG":
        return 1
    if side == "SHORT":
        return -1
    raise ValueError("side must be LONG or SHORT")


def _close_breaks(candle: dict, level: float, side: str, buffer: float) -> bool:
    return candle["close"] > level + buffer if side == "LONG" else candle["close"] < level - buffer


def _daily_gate(d1: list[dict], cfg: ICTMTFConfig) -> tuple[str | None, dict[str, Any]]:
    bias = daily_bias(d1)
    allowed = {"BULLISH", "BEARISH"}
    if cfg.allow_weak_daily:
        allowed |= {"BULLISH_WEAK", "BEARISH_WEAK"}
    if bias.state not in allowed:
        return None, asdict(bias)
    return ("LONG" if bias.state in {"BULLISH", "BULLISH_WEAK"} else "SHORT"), asdict(bias)


def _h1_liquidity_sweeps(h1: list[dict], side: str, cfg: ICTMTFConfig) -> list[dict[str, Any]]:
    """Find closed H1 sweep/reclaims from confirmed, non-micro pivots."""
    if len(h1) < cfg.h1_swing_length * 2 + 2:
        return []
    pools = liquidity_pools(h1, len(h1) - 1, cfg.h1_swing_length)
    wanted = "SELL_SIDE" if side == "LONG" else "BUY_SIDE"
    result = []
    start = max(0, len(h1) - cfg.h1_liquidity_lookback)
    atr = _atr(h1, len(h1) - 1)
    for pool in pools:
        if pool["side"] != wanted or pool["confirmed_idx"] < start:
            continue
        for idx in range(max(pool["confirmed_idx"] + 1, start), len(h1)):
            candle = h1[idx]
            swept = candle["low"] < pool["price"] - cfg.m5_sweep_buffer_atr * atr if side == "LONG" else candle["high"] > pool["price"] + cfg.m5_sweep_buffer_atr * atr
            reclaimed = candle["close"] >= pool["price"] if side == "LONG" else candle["close"] <= pool["price"]
            if swept and reclaimed:
                result.append({"idx": idx, "pool": pool, "extreme": candle["low"] if side == "LONG" else candle["high"]})
    return result


def find_h1_poi(h1: list[dict], side: str, cfg: ICTMTFConfig = ICTMTFConfig()) -> H1POI | None:
    """Return the newest aligned H1 FVG after an H1 liquidity sweep.

    Premium/discount is measured against the latest confirmed H1 swing range;
    an aligned long POI must be in discount and an aligned short POI in premium.
    """
    cfg.validate()
    if side not in {"LONG", "SHORT"} or len(h1) < max(30, cfg.h1_swing_length * 2 + 5):
        return None
    last = len(h1) - 1
    sweeps = _h1_liquidity_sweeps(h1, side, cfg)
    if not sweeps:
        return None
    pivots = _alternating(confirmed_pivots(h1, last, cfg.h1_swing_length))
    if not pivots:
        return None
    range_high = max(p.price for p in pivots)
    range_low = min(p.price for p in pivots)
    eq = (range_high + range_low) / 2
    atr = _atr(h1, last)
    tolerance = cfg.h1_poi_tolerance_atr * atr
    for sweep in reversed(sweeps):
        if last - sweep["idx"] > cfg.h1_poi_max_age:
            continue
        for idx in range(last, sweep["idx"], -1):
            fvg = detect_fvg(h1, idx, "BULLISH" if side == "LONG" else "BEARISH", min_width_atr=cfg.h1_fvg_min_atr)
            if not fvg or fvg.created_idx <= sweep["idx"]:
                continue
            mid = (fvg.bottom + fvg.top) / 2
            location = "DISCOUNT" if mid <= eq else "PREMIUM"
            if (side == "LONG" and location != "DISCOUNT") or (side == "SHORT" and location != "PREMIUM"):
                continue
            current = h1[last]["close"]
            near = fvg.bottom - tolerance <= current <= fvg.top + tolerance
            if not near:
                continue
            return H1POI(side, fvg.bottom, fvg.top, idx, sweep["idx"], asdict(fvg), location)
    return None


def fib_ote(origin: float, extreme: float, side: str, cfg: ICTMTFConfig = ICTMTFConfig()) -> FibZone:
    """Build Fib from the 5M displacement leg, never from an arbitrary range."""
    cfg.validate()
    if side == "LONG":
        distance = extreme - origin
        if distance <= 0:
            raise ValueError("long displacement extreme must exceed origin")
        return FibZone(side, origin, extreme, extreme - distance * cfg.fib_equilibrium, extreme - distance * cfg.fib_ote_high, extreme - distance * cfg.fib_ote_low)
    distance = origin - extreme
    if distance <= 0:
        raise ValueError("short displacement extreme must be below origin")
    return FibZone(side, origin, extreme, extreme + distance * cfg.fib_equilibrium, extreme + distance * cfg.fib_ote_low, extreme + distance * cfg.fib_ote_high)


def _m5_sweep_and_bos(m5: list[dict], poi: H1POI, side: str, cfg: ICTMTFConfig) -> dict[str, Any] | None:
    """Find sweep inside POI, close-confirmed BOS, and strong displacement."""
    last = len(m5) - 1
    if last < cfg.m5_swing_length * 2 + 5:
        return None
    atr = _atr(m5, last)
    pools = liquidity_pools(m5, last, cfg.m5_swing_length)
    wanted = "SELL_SIDE" if side == "LONG" else "BUY_SIDE"
    for pool in reversed([p for p in pools if p["side"] == wanted]):
        for sweep_idx in range(max(pool["confirmed_idx"] + 1, last - cfg.m5_sweep_lookback), last + 1):
            sweep = m5[sweep_idx]
            in_poi = sweep["low"] <= poi.top + cfg.h1_poi_tolerance_atr * atr if side == "LONG" else sweep["high"] >= poi.bottom - cfg.h1_poi_tolerance_atr * atr
            swept = sweep["low"] < pool["price"] - cfg.m5_sweep_buffer_atr * atr if side == "LONG" else sweep["high"] > pool["price"] + cfg.m5_sweep_buffer_atr * atr
            reclaimed = sweep["close"] >= pool["price"] if side == "LONG" else sweep["close"] <= pool["price"]
            if not (in_poi and swept and reclaimed):
                continue
            prior = _alternating(confirmed_pivots(m5, sweep_idx - 1, cfg.m5_swing_length))
            # For a long reversal the valid pre-sweep protected level is a
            # confirmed high; for a short reversal it is a confirmed low.
            candidates = [p for p in prior if p.side == ("HIGH" if side == "LONG" else "LOW")]
            if not candidates:
                continue
            level = candidates[-1].price
            for bos_idx in range(sweep_idx + 1, last + 1):
                bos_atr = _atr(m5, bos_idx)
                if not _close_breaks(m5[bos_idx], level, side, cfg.m5_bos_buffer_atr * bos_atr):
                    continue
                qualified, mode = _displacement_qualified(m5, bos_idx, bos_atr, cfg.m5_displacement_body_atr, cfg.m5_displacement_body_range, cfg.m5_two_bar_displacement_atr)
                if not qualified:
                    continue
                origin = sweep["low"] if side == "LONG" else sweep["high"]
                extreme = max(x["high"] for x in m5[sweep_idx:bos_idx + 1]) if side == "LONG" else min(x["low"] for x in m5[sweep_idx:bos_idx + 1])
                return {"sweep_idx": sweep_idx, "bos_idx": bos_idx, "bos_level": level, "origin": origin, "extreme": extreme, "displacement_mode": mode, "pool": pool}
    return None


def evaluate_ict_mtf(d1: list[dict], h1: list[dict], m5: list[dict], cfg: ICTMTFConfig = ICTMTFConfig()) -> dict[str, Any] | None:
    """Evaluate only the final closed M5 candle; no entry on BOS itself."""
    cfg.validate()
    side, bias = _daily_gate(d1, cfg)
    if side is None:
        return None
    poi = find_h1_poi(h1, side, cfg)
    if poi is None:
        return None
    current = m5[-1]
    near_poi = current["low"] <= poi.top and current["high"] >= poi.bottom
    if not near_poi:
        return None
    confirmation = _m5_sweep_and_bos(m5, poi, side, cfg)
    if confirmation is None or confirmation["bos_idx"] >= len(m5) - 1:
        return None
    # CHoCH/MSS is a second, post-BOS close break after a confirmed pullback.
    post_bos = m5[confirmation["bos_idx"] + 1:]
    if len(post_bos) < cfg.m5_swing_length + 1:
        return None
    post_pivots = _alternating(confirmed_pivots(m5, len(m5) - 1, cfg.m5_swing_length))
    follow = [p for p in post_pivots if p.pivot_idx > confirmation["bos_idx"] and p.side == ("HIGH" if side == "LONG" else "LOW")]
    if not follow:
        return None
    mss_level = follow[-1].price
    mss_idx = None
    for idx in range(follow[-1].confirmed_idx, len(m5)):
        a = _atr(m5, idx)
        if _close_breaks(m5[idx], mss_level, side, cfg.m5_bos_buffer_atr * a):
            qualified, mode = _displacement_qualified(m5, idx, a, cfg.m5_displacement_body_atr, cfg.m5_displacement_body_range, cfg.m5_two_bar_displacement_atr)
            if qualified:
                mss_idx = idx
                confirmation["mss_mode"] = mode
                break
    if mss_idx is None or mss_idx >= len(m5) - 1:
        return None
    zone = fib_ote(confirmation["origin"], confirmation["extreme"], side, cfg)
    price = current["close"]
    if not zone.contains(price):
        return None
    if side == "LONG" and current["close"] < zone.ote_high:
        return None
    if side == "SHORT" and current["close"] > zone.ote_high:
        return None
    confluence = detect_fvg(m5, mss_idx, "BULLISH" if side == "LONG" else "BEARISH", min_width_atr=cfg.m5_fvg_min_atr)
    if cfg.require_m5_confluence and confluence is None:
        return None
    weak = bias["state"] in {"BULLISH_WEAK", "BEARISH_WEAK"}
    return {"model": "ICT_MTF_D1_H1_POI_M5_CONFIRMATION", "side": side, "entry_idx": len(m5), "entry_price": price, "daily_bias": bias, "h1_poi": asdict(poi), "confirmation": confirmation, "mss_idx": mss_idx, "fib_ote": asdict(zone), "m5_fvg_confluence": asdict(confluence) if confluence else None, "risk_tier": "REDUCED" if weak else "STANDARD", "risk_multiplier": cfg.weak_daily_risk_multiplier if weak else 1.0}


def rejection_reasons_ict_mtf(d1: list[dict], h1: list[dict], m5: list[dict], cfg: ICTMTFConfig = ICTMTFConfig()) -> list[str]:
    """Causal gate diagnostics for the strict model."""
    cfg.validate()
    side, _ = _daily_gate(d1, cfg)
    if side is None:
        return ["D1_NO_DIRECTIONAL_BIAS"]
    poi = find_h1_poi(h1, side, cfg)
    if poi is None:
        return ["H1_NO_ALIGNED_POI_AFTER_LIQUIDITY"]
    current = m5[-1]
    if not (current["low"] <= poi.top and current["high"] >= poi.bottom):
        return ["M5_NOT_AT_H1_POI"]
    confirmation = _m5_sweep_and_bos(m5, poi, side, cfg)
    if confirmation is None:
        return ["M5_NO_POI_SWEEP_BOS_DISPLACEMENT"]
    if confirmation["bos_idx"] >= len(m5) - 1:
        return ["M5_BOS_NO_POST_BOS_CONFIRMATION"]
    return ["M5_NO_CHoCH_MSS_FIB_ENTRY"]


__all__ = ["ICTMTFConfig", "H1POI", "FibZone", "find_h1_poi", "fib_ote", "evaluate_ict_mtf", "rejection_reasons_ict_mtf"]
