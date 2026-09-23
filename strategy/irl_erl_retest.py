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
    m5_poi_min_atr: float = 0.05
    target_rr: float = 1.50
    allow_weak_daily: bool = False

    def validate(self) -> None:
        if not 0 < self.fib_half < 1:
            raise ValueError("fib_half must be between 0 and 1")
        if self.h1_swing_length < 2 or self.m5_swing_length < 2:
            raise ValueError("swing lengths must be >= 2")
        if self.h1_retest_max_bars < 1 or self.m5_confirmation_lookback < 5:
            raise ValueError("lookback windows are too short")
        if self.target_rr <= 0:
            raise ValueError("target_rr must be positive")


def _side_from_bias(d1: list[dict], cfg: IRLERLConfig) -> tuple[str | None, dict[str, Any]]:
    bias = daily_bias(d1)
    allowed = {"BULLISH", "BEARISH"}
    if cfg.allow_weak_daily:
        allowed |= {"BULLISH_WEAK", "BEARISH_WEAK"}
    if bias.state not in allowed:
        return None, asdict(bias)
    return ("LONG" if bias.state in {"BULLISH", "BULLISH_WEAK"} else "SHORT"), asdict(bias)


def _find_internal_poi(h1: list[dict], side: str, cfg: IRLERLConfig) -> dict[str, Any] | None:
    """Find IRL/POI only after a confirmed external-liquidity sweep."""
    if len(h1) < max(30, cfg.h1_swing_length * 2 + 5):
        return None
    wanted = "BULLISH" if side == "LONG" else "BEARISH"
    pivots = _alternating(confirmed_pivots(h1, len(h1) - 1, cfg.h1_swing_length))
    if not pivots:
        return None
    high = max(p.price for p in pivots)
    low = min(p.price for p in pivots)
    eq = (high + low) / 2
    external_side = "HIGH" if side == "LONG" else "LOW"
    externals = [p for p in pivots if p.side == external_side]
    # Only the latest confirmed external levels are candidates for the
    # currently forming dealing range; scanning the whole history repeatedly
    # at every M5 close is both unnecessary and computationally explosive.
    recent_externals = externals[-5:]
    for external in reversed(recent_externals):
        for sweep_idx in range(max(external.confirmed_idx + 1, len(h1) - cfg.h1_external_lookback), len(h1)):
            sweep = h1[sweep_idx]
            took = sweep["high"] > external.price + cfg.h1_sweep_buffer_atr * _atr(h1, sweep_idx) if side == "LONG" else sweep["low"] < external.price - cfg.h1_sweep_buffer_atr * _atr(h1, sweep_idx)
            if not took:
                continue
            for idx in range(len(h1) - 1, max(sweep_idx, len(h1) - cfg.h1_external_lookback), -1):
                fvg = detect_fvg(h1, idx, wanted, min_width_atr=cfg.h1_fvg_min_atr)
                if not fvg:
                    continue
                mid = (fvg.bottom + fvg.top) / 2
                location = "DISCOUNT" if mid <= eq else "PREMIUM"
                if (side == "LONG" and location == "DISCOUNT") or (side == "SHORT" and location == "PREMIUM"):
                    return {"side": side, "bottom": fvg.bottom, "top": fvg.top, "created_idx": idx, "fvg": asdict(fvg), "location": location, "range_low": low, "range_high": high, "external_level": external.price, "external_pivot_idx": external.pivot_idx, "sweep_idx": sweep_idx}
    return None


def _external_sweep_and_retest(h1: list[dict], poi: dict[str, Any], side: str, cfg: IRLERLConfig) -> dict[str, Any] | None:
    """Validate range after ERL is taken and price reaches Fib 50%.

    A wick/touch is sufficient. H1 close location around 50% is intentionally
    not a gate; M5 BOS -> CHoCH is the execution confirmation.
    """
    if "sweep_idx" not in poi or "external_level" not in poi:
        return None
    start = poi["sweep_idx"] + 1
    end = min(len(h1), start + cfg.h1_retest_max_bars)
    sweep_idx = poi["sweep_idx"]
    extreme = max(h1[j]["high"] for j in range(poi["external_pivot_idx"], sweep_idx + 1)) if side == "LONG" else min(h1[j]["low"] for j in range(poi["external_pivot_idx"], sweep_idx + 1))
    origin = poi["bottom"] if side == "LONG" else poi["top"]
    if (side == "LONG" and extreme <= origin) or (side == "SHORT" and extreme >= origin):
        return {"state": "EXTERNAL_SWEPT_NO_VALID_RETEST", "external_level": poi["external_level"]}
    half = origin + (extreme - origin) * cfg.fib_half if side == "LONG" else origin - (origin - extreme) * cfg.fib_half
    for retest_idx in range(start, end):
        bar = h1[retest_idx]
        crossed = bar["low"] <= half if side == "LONG" else bar["high"] >= half
        if crossed:
            return {"state": "TOUCHED_FIFTY", "sweep_idx": sweep_idx, "retest_idx": retest_idx, "external_level": poi["external_level"], "half": half, "origin": origin, "extreme": extreme}
    return {"state": "EXTERNAL_SWEPT_NO_VALID_RETEST", "external_level": poi["external_level"]}


def _m5_bos_choch(m5: list[dict], side: str, cfg: IRLERLConfig) -> dict[str, Any] | None:
    """Require M5 liquidity sweep -> close BOS -> later displaced CHoCH.

    MSS is intentionally not used as an M5 gate. The returned POI must be an
    FVG created inside the BOS-to-CHoCH leg, and the target is a confirmed new
    swing liquidity level formed after CHoCH.
    """
    if len(m5) < max(40, cfg.m5_swing_length * 2 + 10):
        return None
    last = len(m5) - 1
    pivots = _alternating(confirmed_pivots(m5, last, cfg.m5_swing_length))
    if not pivots:
        return None
    opposite = "HIGH" if side == "LONG" else "LOW"
    levels = [p for p in pivots if p.side == opposite]
    if not levels:
        return None
    # M5 uses only close-confirmed BOS followed by close-confirmed CHoCH.
    # Liquidity/ERL validation remains on H1; no M5 MSS or sweep gate here.
    prior_levels = [p for p in levels if p.confirmed_idx < last - 1]
    if not prior_levels:
        return None
    bos_level = prior_levels[-1].price
    bos_candidates = [idx for idx in range(max(1, last - cfg.m5_confirmation_lookback), last) if _close_breaks_m5(m5[idx], bos_level, side, cfg.m5_break_buffer_atr * _atr(m5, idx))]
    for bos_idx in bos_candidates:
        later = [p for p in pivots if p.pivot_idx > bos_idx and p.side == opposite]
        if not later:
            continue
        choch_level = later[-1].price
        for idx in range(later[-1].confirmed_idx, last):
            if _close_breaks_m5(m5[idx], choch_level, side, cfg.m5_break_buffer_atr * _atr(m5, idx)):
                poi = None
                wanted = "BULLISH" if side == "LONG" else "BEARISH"
                for poi_idx in range(idx, bos_idx, -1):
                    fvg = detect_fvg(m5, poi_idx, wanted, min_width_atr=cfg.m5_poi_min_atr)
                    if fvg and fvg.created_idx > bos_idx:
                        poi = {"bottom": fvg.bottom, "top": fvg.top, "created_idx": poi_idx, "fvg": asdict(fvg)}
                        break
                post_pivots = _alternating(confirmed_pivots(m5, last, cfg.m5_swing_length))
                target_side = "HIGH" if side == "LONG" else "LOW"
                targets = [p for p in post_pivots if p.pivot_idx > idx and p.side == target_side]
                target = targets[-1].price if targets else None
                sl = min(x["low"] for x in m5[:bos_idx + 1]) if side == "LONG" else max(x["high"] for x in m5[:bos_idx + 1])
                return {"bos_idx": bos_idx, "choch_idx": idx, "bos_level": bos_level, "choch_level": choch_level, "m5_poi": poi, "sl": sl, "target": target}
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
    if not range_check or range_check.get("state") != "TOUCHED_FIFTY":
        return None
    confirmation = _m5_bos_choch(m5, side, cfg)
    if confirmation is None:
        return None
    m5_poi = confirmation.get("m5_poi")
    if m5_poi is None:
        return None
    current = m5[-1]
    if current["high"] < m5_poi["bottom"] or current["low"] > m5_poi["top"]:
        return None
    entry = current["close"]
    sl = confirmation["sl"]
    target = confirmation.get("target")
    risk = entry - sl if side == "LONG" else sl - entry
    if risk <= 0 or target is None:
        return None
    if (side == "LONG" and target < entry + cfg.target_rr * risk) or (side == "SHORT" and target > entry - cfg.target_rr * risk):
        return None
    return {"model": "IRL_ERL_H1_50_CLOSE_M5_BOS_CHOCH", "side": side, "entry_price": entry, "stop_loss": sl, "target": target, "target_rr": cfg.target_rr, "daily_bias": bias, "internal_poi": poi, "range_validation": range_check, "m5_confirmation": confirmation, "risk_tier": "STANDARD" if bias["strength"] != "WEAK_LOCATION" else "REDUCED", "risk_multiplier": 1.0 if bias["strength"] != "WEAK_LOCATION" else 0.5}


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
    if check.get("state") != "TOUCHED_FIFTY":
        return ["H1_NO_FIFTY_TOUCH"]
    confirmation = _m5_bos_choch(m5, side, cfg)
    if confirmation is None:
        return ["M5_NO_BOS_CHOCH"]
    if confirmation.get("m5_poi") is None:
        return ["M5_NO_POI_INSIDE_BOS_CHOCH_LEG"]
    current = m5[-1]
    m5_poi = confirmation["m5_poi"]
    if current["high"] < m5_poi["bottom"] or current["low"] > m5_poi["top"]:
        return ["M5_POI_NO_RETEST"]
    entry = current["close"]
    sl = confirmation["sl"]
    target = confirmation.get("target")
    risk = entry - sl if side == "LONG" else sl - entry
    if risk <= 0:
        return ["M5_INVALID_STOP_DISTANCE"]
    if target is None:
        return ["M5_NO_NEW_LIQUIDITY_TARGET"]
    if (side == "LONG" and target < entry + cfg.target_rr * risk) or (side == "SHORT" and target > entry - cfg.target_rr * risk):
        return ["M5_TARGET_BELOW_MINIMUM_RR"]
    return ["NO_ENTRY_REJECTION_UNCLASSIFIED"]


__all__ = ["IRLERLConfig", "evaluate_irl_erl_retest", "rejection_reasons_irl_erl"]
