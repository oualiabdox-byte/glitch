"""Calibrated ICT/SMC hybrid entry logic.

Design reference:
- 4H directional context
- liquidity sweep OR directional displacement
- confirmed post-event BOS/CHoCH
- FVG or Order Block retest when available
- liquidity target when available, otherwise structural 2R
- premium/discount, session and DOL are contextual confluence, not hard gates

The model intentionally keeps the SMC concepts modular. The core trigger is
not allowed to become an all-filters stack, which helps preserve trade
frequency and reduces parameter overfitting. All calculations are causal.
"""

from .ict_strategy import _atr, _pip_size, _find_recent_sweep
from . import ict_bias, market_structure, liquidity, fvg, displacement, order_blocks, dominating_candle


def _post_event_structure(recent, event_idx, side, swing_length=3):
    """Return (confirmed, level, break_idx) using only confirmed swings."""
    if event_idx < swing_length * 2 + 1:
        return False, None, None

    pre = recent[:event_idx + 1]
    post = recent[event_idx + 1:]
    if not post:
        return False, None, None

    if side == "LONG":
        swings = market_structure.find_swing_highs(pre, length=swing_length)
        if not swings:
            return False, None, None
        level = swings[-1]["high"]
        for i, c in enumerate(post, start=event_idx + 1):
            if c["close"] > level:
                return True, level, i
    else:
        swings = market_structure.find_swing_lows(pre, length=swing_length)
        if not swings:
            return False, None, None
        level = swings[-1]["low"]
        for i, c in enumerate(post, start=event_idx + 1):
            if c["close"] < level:
                return True, level, i

    return False, level, None


def _fvg_retested(recent, zone, side):
    """Require the current candle to be the first post-creation mitigation."""
    if not zone or zone["creator_idx"] >= len(recent) - 1:
        return False

    prior = recent[zone["creator_idx"] + 2:-1]
    cur = recent[-1]

    if side == "LONG":
        if any(c["low"] <= zone["top"] for c in prior):
            return False
        return cur["low"] <= zone["top"] and cur["close"] >= zone["bottom"]

    if any(c["high"] >= zone["bottom"] for c in prior):
        return False
    return cur["high"] >= zone["bottom"] and cur["close"] <= zone["top"]


def _ob_retested(recent, ob, side):
    """Require a fresh OB reaction and reject a previously broken zone."""
    if not ob:
        return False

    prior = recent[ob["idx"] + 1:-1]
    cur = recent[-1]

    if side == "LONG":
        if any(c["close"] < ob["bottom"] for c in prior):
            return False
        return cur["low"] <= ob["top"] and cur["close"] >= ob["bottom"]

    if any(c["close"] > ob["top"] for c in prior):
        return False
    return cur["high"] >= ob["bottom"] and cur["close"] <= ob["top"]


def _confluence_context(candles_1h, candles_4h, bias, current, session_context):
    """Return non-blocking SMC confluence facts.

    These facts are deliberately reported rather than independently required.
    This prevents the common overfitting failure where PD + session + DOL +
    FVG + sweep all become mandatory and produce zero trades.
    """
    dealing = candles_4h[-6:]
    low = min(c["low"] for c in dealing)
    high = max(c["high"] for c in dealing)
    rng = high - low
    position = (current - low) / rng if rng > 0 else 0.5

    if bias == "LONG":
        pd_zone = "discount" if position < 0.50 else "premium"
    else:
        pd_zone = "premium" if position > 0.50 else "discount"

    pools = liquidity.liquidity_pools(candles_4h[-30:])
    directional = [
        p for p in pools
        if (
            bias == "LONG"
            and p["type"] == "resistance"
            and p["price"] > current
        )
        or (
            bias == "SHORT"
            and p["type"] == "support"
            and p["price"] < current
        )
    ]

    # Context score is descriptive only: it is never used as a hidden
    # optimizer or pair-specific threshold.
    score = 0
    if pd_zone == ("discount" if bias == "LONG" else "premium"):
        score += 1
    if session_context in ("london", "new_york", "overlap"):
        score += 1
    if directional:
        score += 1

    return {
        "premium_discount_zone": pd_zone,
        "session_valid": session_context in ("london", "new_york", "overlap"),
        "dol_available": bool(directional),
        "confluence_score": score,
        "confluence_max": 3,
    }


def evaluate_ict_hybrid(
    candles_1h,
    candles_4h,
    pair,
    min_rr=1.5,
    min_displacement_atr=0.90,
    min_fvg_atr=0.03,
    stop_atr_buffer=0.10,
    require_session=False,
    session_context=None,
    dc_timeframe="1h",
    dc_min_contained=3,
    dc_lookback=8,
):
    """Calibrated SMC entry model.

    Mandatory core:
      1. 4H directional bias
      2. liquidity sweep OR directional displacement
      3. post-event BOS/CHoCH

    Entry hierarchy:
      FVG retest -> OB retest -> confirmed structure-reclaim.

    SMC context:
      premium/discount, session and draw-on-liquidity are recorded as
      confluence, but are not hard gates unless explicitly requested.
    """
    if len(candles_1h) < 30 or len(candles_4h) < 30:
        return None

    bias = ict_bias.htf_bias_4h(candles_4h)
    if bias not in ("LONG", "SHORT"):
        return None

    if require_session and session_context not in ("london", "new_york", "overlap"):
        return None

    recent = candles_1h[-48:]
    sweep = _find_recent_sweep(recent, bias, lookback=16, reference_bars=5)

    event_idx = None
    event_type = None
    if sweep:
        event_idx = next(
            (i for i, c in enumerate(recent) if c["time"] == sweep["time"]),
            None,
        )
        event_type = "LIQUIDITY_SWEEP"

    # A clean directional displacement can initiate the sequence when no
    # recent liquidity sweep is present.
    if event_idx is None:
        for i in range(len(recent) - 2, max(0, len(recent) - 14), -1):
            c = recent[i]
            if displacement.is_displaced(
                recent, i, min_body_atr_ratio=min_displacement_atr
            ) and (
                (bias == "LONG" and c["close"] > c["open"])
                or (bias == "SHORT" and c["close"] < c["open"])
            ):
                event_idx = i
                event_type = "DISPLACEMENT"
                break

    if event_idx is None:
        return None

    mss, mss_level, break_idx = _post_event_structure(
        recent, event_idx, bias, swing_length=3
    )
    if not mss:
        return None

    fvg_result = fvg.find_fvg(
        recent,
        min_gap_atr=min_fvg_atr,
        required_side=bias,
        displacement_min_atr=min_displacement_atr,
    )
    if fvg_result and fvg_result["creator_idx"] <= event_idx:
        fvg_result = None

    fvg_retest = _fvg_retested(recent, fvg_result, bias)
    ob_result = order_blocks.find_order_block(recent, fvg_result) if fvg_result else None
    ob_retest = _ob_retested(recent, ob_result, bias)

    if fvg_retest:
        entry_mid = (fvg_result["bottom"] + fvg_result["top"]) / 2.0
        entry_zone = (fvg_result["bottom"], fvg_result["top"])
        trigger = "FVG_RETEST"
    elif ob_retest:
        entry_mid = (ob_result["bottom"] + ob_result["top"]) / 2.0
        entry_zone = (ob_result["bottom"], ob_result["top"])
        trigger = "OB_RETEST"
    else:
        entry_mid = recent[-1]["close"]
        entry_zone = (entry_mid, entry_mid)
        trigger = "CHOCH_RECLAIM"

    atr = _atr(recent, 14)
    if atr <= 0:
        return None

    if sweep:
        extreme = sweep["extreme"]
    else:
        post = recent[event_idx + 1:]
        if not post:
            return None
        extreme = (
            min(c["low"] for c in post[-5:])
            if bias == "LONG"
            else max(c["high"] for c in post[-5:])
        )

    buffer = max(atr * stop_atr_buffer, _pip_size(pair))
    stop = extreme - buffer if bias == "LONG" else extreme + buffer

    context = _confluence_context(
        candles_1h, candles_4h, bias, recent[-1]["close"], session_context
    )

    # Dominating Candle is a non-blocking structural confluence. The source
    # logic is range-containment, not a classic two-candle engulfing pattern.
    dc_context = dominating_candle.dc_context(
        recent, min_contained=dc_min_contained, lookback=dc_lookback
    )
    dc = dc_context["dc"]
    dc_break = dc_context["dc_breakout"]
    dc_aligned = bool(dc_break and dc_break == bias)

    # Add DC to the descriptive confluence score only. It is deliberately
    # NOT a mandatory gate, preventing the SMC stack from collapsing to zero
    # trades on sparse historical samples.
    if dc_aligned:
        context["confluence_score"] += 1
    context["confluence_max"] = 4
    context.update({
        "dc_valid": bool(dc),
        "dc_breakout": dc_break,
        "dc_aligned": dc_aligned,
        "dc_low": dc["low"] if dc else None,
        "dc_high": dc["high"] if dc else None,
        "dc_time": dc["time"] if dc else None,
        "dc_contained_bars": dc["contained_bars"] if dc else 0,
    })

    pools = liquidity.liquidity_pools(candles_4h[-30:])
    current = recent[-1]["close"]
    directional = [
        p for p in pools
        if (
            bias == "LONG"
            and p["type"] == "resistance"
            and p["price"] > current
        )
        or (
            bias == "SHORT"
            and p["type"] == "support"
            and p["price"] < current
        )
    ]
    target_pool = (
        min(directional, key=lambda p: abs(p["price"] - current))
        if directional
        else None
    )

    risk = entry_mid - stop if bias == "LONG" else stop - entry_mid
    if risk <= 0:
        return None

    target = (
        target_pool["price"]
        if target_pool
        else (
            entry_mid + 2.0 * risk
            if bias == "LONG"
            else entry_mid - 2.0 * risk
        )
    )
    reward = target - entry_mid if bias == "LONG" else entry_mid - target
    if reward <= 0:
        return None

    rr = reward / risk
    if rr < min_rr:
        return None

    return {
        "pair": pair,
        "side": bias,
        "entry_zone": entry_zone,
        "entry_mid": entry_mid,
        "stop_price": stop,
        "stop_ref": extreme,
        "tp_target": target,
        "target_source": target_pool["source"] if target_pool else "STRUCTURAL_2R",
        "rr": rr,
        "bias": bias,
        "session": session_context,
        "fvg": fvg_result if fvg_retest else None,
        "order_block": ob_result if ob_retest else None,
        "mss_confirmed": True,
        "mss_level": mss_level,
        "mss_break_idx": break_idx,
        "event_type": event_type,
        "displacement_confirmed": event_type == "DISPLACEMENT" or (
            fvg_result is not None
        ),
        "entry_trigger": trigger,
        **context,
        "timestamp": candles_1h[-1]["time"],
    }
