"""Side-by-side IRL -> ERL range/Fibonacci validation model.

This model is deliberately separate from ``strict_ict_mtf``. It treats an
external-liquidity run as a *range validation event*, not as the initial H1
POI detector. For a long setup, after an H1 FVG (internal range liquidity) and
a later external swing-high sweep, the H1 retest must wick below 50% and close
back above 50%. A close below 50% invalidates the range. Shorts are mirrored.
Only then does a closed-bar M5 BOS+CHoCH confirmation qualify an entry.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .multi_timeframe import _atr, _alternating, _body_metrics, _displacement_qualified, confirmed_pivots, daily_bias, detect_fvg


@dataclass(frozen=True)
class IRLERLConfig:
    h1_swing_length: int = 5
    h1_fvg_min_atr: float = 0.10
    h1_external_lookback: int = 72
    h1_sweep_buffer_atr: float = 0.10
    h1_retest_max_bars: int = 24
    fib_half: float = 0.50
    m5_swing_length: int = 3
    m5_confirmation_lookback: int = 36
    m5_break_buffer_atr: float = 0.10
    m5_displacement_body_atr: float = 0.75
    m5_displacement_body_range: float = 0.50
    m5_two_bar_displacement_atr: float = 1.00
    allow_weak_daily: bool = False

    def validate(self) -> None:
        if not 0 < self.fib_half < 1:
            raise ValueError("fib_half must be between 0 and 1")
        if self.h1_swing_length < 2 or self.m5_swing_length < 2:
            raise ValueError("swing lengths must be >= 2")
        if self.h1_retest_max_bars < 1 or self.m5_confirmation_lookback < 5:
            raise ValueError("lookback windows are too short")


def _side_from_bias(d1: list[dict], cfg: IRLERLConfig) -> tuple[str | None, dict[str, Any]]:
    bias = daily_bias(d1)
    allowed = {"BULLISH", "BEARISH"}
    if cfg.allow_weak_daily:
        allowed |= {"BULLISH_WEAK", "BEARISH_WEAK"}
    if bias.state not in allowed:
        return None, asdict(bias)
    return ("LONG" if bias.state in {"BULLISH", "BULLISH_WEAK"} else "SHORT"), asdict(bias)


def _find_internal_poi(h1: list[dict], side: str, cfg: IRLERLConfig) -> dict[str, Any] | None:
    """Find a directional H1 FVG without requiring external liquidity first."""
    if len(h1) < max(30, cfg.h1_swing_length * 2 + 5):
        return None
    wanted = "BULLISH" if side == "LONG" else "BEARISH"
    pivots = _alternating(confirmed_pivots(h1, len(h1) - 1, cfg.h1_swing_length))
    if not pivots:
        return None
    high = max(p.price for p in pivots)
    low = min(p.price for p in pivots)
    eq = (high + low) / 2
    for idx in range(len(h1) - 1, 1, -1):
        fvg = detect_fvg(h1, idx, wanted, min_width_atr=cfg.h1_fvg_min_atr)
        if not fvg:
            continue
        mid = (fvg.bottom + fvg.top) / 2
        location = "DISCOUNT" if mid <= eq else "PREMIUM"
        if (side == "LONG" and location == "DISCOUNT") or (side == "SHORT" and location == "PREMIUM"):
            return {"side": side, "bottom": fvg.bottom, "top": fvg.top, "created_idx": idx, "fvg": asdict(fvg), "location": location, "range_low": low, "range_high": high}
    return None


def _external_sweep_and_retest(h1: list[dict], poi: dict[str, Any], side: str, cfg: IRLERLConfig) -> dict[str, Any] | None:
    """Validate range only after external swing liquidity is taken."""
    pivots = _alternating(confirmed_pivots(h1, len(h1) - 1, cfg.h1_swing_length))
    pivot_side = "HIGH" if side == "LONG" else "LOW"
    candidates = [p for p in pivots if p.side == pivot_side and p.pivot_idx > poi["created_idx"]]
    if not candidates:
        return None
    external = candidates[-1]
    start = external.confirmed_idx + 1
    end = min(len(h1), start + cfg.h1_retest_max_bars)
    atr = _atr(h1, len(h1) - 1)
    for sweep_idx in range(start, min(len(h1), start + cfg.h1_external_lookback)):
        sweep = h1[sweep_idx]
        took = sweep["high"] > external.price + cfg.h1_sweep_buffer_atr * atr if side == "LONG" else sweep["low"] < external.price - cfg.h1_sweep_buffer_atr * atr
        if not took:
            continue
        extreme = max(h1[j]["high"] for j in range(external.pivot_idx, sweep_idx + 1)) if side == "LONG" else min(h1[j]["low"] for j in range(external.pivot_idx, sweep_idx + 1))
        origin = poi["bottom"] if side == "LONG" else poi["top"]
        if (side == "LONG" and extreme <= origin) or (side == "SHORT" and extreme >= origin):
            continue
        half = origin + (extreme - origin) * cfg.fib_half if side == "LONG" else origin - (origin - extreme) * cfg.fib_half
        for retest_idx in range(sweep_idx + 1, end):
            bar = h1[retest_idx]
            if side == "LONG":
                crossed = bar["low"] <= half
                valid_close = bar["close"] > half
                invalid = bar["close"] < half
            else:
                crossed = bar["high"] >= half
                valid_close = bar["close"] < half
                invalid = bar["close"] > half
            if invalid:
                return {"state": "INVALIDATED_CLOSE_WRONG_SIDE", "sweep_idx": sweep_idx, "retest_idx": retest_idx, "external_level": external.price, "half": half}
            if crossed and valid_close:
                return {"state": "VALIDATED_CLOSE_ABOVE_BELOW_50", "sweep_idx": sweep_idx, "retest_idx": retest_idx, "external_level": external.price, "half": half, "origin": origin, "extreme": extreme}
    return {"state": "EXTERNAL_SWEPT_NO_VALID_RETEST", "external_level": external.price}


def _m5_bos_choch(m5: list[dict], side: str, cfg: IRLERLConfig) -> dict[str, Any] | None:
    """Require a 5M sweep, BOS close, then a later displaced CHoCH/MSS close."""
    if len(m5) < max(40, cfg.m5_swing_length * 2 + 10):
        return None
    last = len(m5) - 1
    pivots = _alternating(confirmed_pivots(m5, last, cfg.m5_swing_length))
    if not pivots:
        return None
    opposite = "HIGH" if side == "LONG" else "LOW"
    pools = [p for p in pivots if p.side == ("LOW" if side == "LONG" else "HIGH")]
    levels = [p for p in pivots if p.side == opposite]
    if not pools or not levels:
        return None
    atr = _atr(m5, last)
    for pool in reversed(pools):
        for sweep_idx in range(max(pool.confirmed_idx + 1, last - cfg.m5_confirmation_lookback), last - 2):
            sweep = m5[sweep_idx]
            swept = sweep["low"] < pool.price - cfg.m5_break_buffer_atr * atr if side == "LONG" else sweep["high"] > pool.price + cfg.m5_break_buffer_atr * atr
            reclaimed = sweep["close"] >= pool.price if side == "LONG" else sweep["close"] <= pool.price
            if not (swept and reclaimed):
                continue
            prior_levels = [p for p in levels if p.confirmed_idx < sweep_idx]
            if not prior_levels:
                continue
            bos_level = prior_levels[-1].price
            bos_idx = None
            for idx in range(sweep_idx + 1, last):
                a = _atr(m5, idx)
                if _close_breaks_m5(m5[idx], bos_level, side, cfg.m5_break_buffer_atr * a):
                    ok, mode = _displacement_qualified(m5, idx, a, cfg.m5_displacement_body_atr, cfg.m5_displacement_body_range, cfg.m5_two_bar_displacement_atr)
                    if ok:
                        bos_idx = idx
                        break
            if bos_idx is None:
                continue
            later = [p for p in pivots if p.pivot_idx > bos_idx and p.side == opposite]
            if not later:
                continue
            mss_level = later[-1].price
            for idx in range(later[-1].confirmed_idx, last + 1):
                a = _atr(m5, idx)
                if _close_breaks_m5(m5[idx], mss_level, side, cfg.m5_break_buffer_atr * a):
                    ok, mss_mode = _displacement_qualified(m5, idx, a, cfg.m5_displacement_body_atr, cfg.m5_displacement_body_range, cfg.m5_two_bar_displacement_atr)
                    if ok:
                        return {"sweep_idx": sweep_idx, "bos_idx": bos_idx, "mss_idx": idx, "bos_level": bos_level, "mss_level": mss_level, "bos_mode": mode, "mss_mode": mss_mode}
    return None


def _close_breaks_m5(candle: dict, level: float, side: str, buffer: float) -> bool:
    return candle["close"] > level + buffer if side == "LONG" else candle["close"] < level - buffer


def evaluate_irl_erl_retest(d1: list[dict], h1: list[dict], m5: list[dict], cfg: IRLERLConfig = IRLERLConfig()) -> dict[str, Any] | None:
    """Evaluate the side model on closed bars only."""
    cfg.validate()
    side, bias = _side_from_bias(d1, cfg)
    if side is None:
        return None
    poi = _find_internal_poi(h1, side, cfg)
    if poi is None:
        return None
    range_check = _external_sweep_and_retest(h1, poi, side, cfg)
    if not range_check or range_check.get("state") != "VALIDATED_CLOSE_ABOVE_BELOW_50":
        return None
    confirmation = _m5_bos_choch(m5, side, cfg)
    if confirmation is None:
        return None
    return {"model": "IRL_ERL_H1_50_CLOSE_M5_BOS_CHOCH", "side": side, "daily_bias": bias, "internal_poi": poi, "range_validation": range_check, "m5_confirmation": confirmation, "risk_tier": "STANDARD" if bias["strength"] != "WEAK_LOCATION" else "REDUCED", "risk_multiplier": 1.0 if bias["strength"] != "WEAK_LOCATION" else 0.5}


def rejection_reasons_irl_erl(d1: list[dict], h1: list[dict], m5: list[dict], cfg: IRLERLConfig = IRLERLConfig()) -> list[str]:
    cfg.validate()
    side, _ = _side_from_bias(d1, cfg)
    if side is None:
        return ["D1_NO_DIRECTIONAL_BIAS"]
    poi = _find_internal_poi(h1, side, cfg)
    if poi is None:
        return ["H1_NO_INTERNAL_POI"]
    check = _external_sweep_and_retest(h1, poi, side, cfg)
    if not check:
        return ["H1_NO_EXTERNAL_LIQUIDITY_SWEEP"]
    if check.get("state") == "EXTERNAL_SWEPT_NO_VALID_RETEST":
        return ["H1_EXTERNAL_SWEEP_NO_VALID_RETEST"]
    if check.get("state") == "INVALIDATED_CLOSE_WRONG_SIDE":
        return ["H1_CLOSE_WRONG_SIDE_OF_50"]
    if check.get("state") != "VALIDATED_CLOSE_ABOVE_BELOW_50":
        return ["H1_RANGE_NOT_VALIDATED"]
    if _m5_bos_choch(m5, side, cfg) is None:
        return ["M5_NO_SWEEP_BOS_CHOCH"]
    return ["NO_ENTRY_REJECTION_UNCLASSIFIED"]


__all__ = ["IRLERLConfig", "evaluate_irl_erl_retest", "rejection_reasons_irl_erl"]
