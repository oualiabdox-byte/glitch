"""Calibrated ICT/SMC hybrid entry logic.

Design reference:
- 4H directional context
- liquidity sweep OR directional displacement
- confirmed post-event structure break
- FVG or Order Block as preferred POI, with close-reclaim fallback
- liquidity target when available, otherwise structural 2R

This deliberately removes the strict model's requirement that every ICT
concept (session, PD, DOL, FVG, displacement threshold) must all agree.
"""

from .ict_strategy import _atr, _pip_size, _find_recent_sweep
from . import ict_bias, market_structure, liquidity, fvg, displacement, order_blocks


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
    if not zone or zone["creator_idx"] >= len(recent) - 1:
        return False
    cur = recent[-1]
    if side == "LONG":
        return cur["low"] <= zone["top"] and cur["close"] >= zone["bottom"]
    return cur["high"] >= zone["bottom"] and cur["close"] <= zone["top"]


def _ob_retested(recent, ob, side):
    if not ob:
        return False
    cur = recent[-1]
    if side == "LONG":
        return cur["low"] <= ob["top"] and cur["close"] >= ob["bottom"]
    return cur["high"] >= ob["bottom"] and cur["close"] <= ob["top"]


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
):
    """Calibrated SMC entry model.

    Mandatory:
      1. 4H directional bias
      2. recent sweep OR directional displacement
      3. post-event BOS/CHoCH-style close through the opposing structure

    Preferred entry:
      FVG retest OR OB retest.

    Relaxation:
      If structure has broken but neither POI is available, a close-reclaim
      entry is allowed. Session, premium/discount and DOL are contextual,
      not hard gates.
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
    if sweep:
        event_idx = next(
            (i for i, c in enumerate(recent) if c["time"] == sweep["time"]),
            None,
        )

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
                break

    if event_idx is None:
        return None

    mss, mss_level, break_idx = _post_event_structure(
        recent, event_idx, bias, swing_length=3
    )
    if not mss:
        return None

    # Find a fresh FVG after the event. The FVG detector itself is causal:
    # its third candle is closed before the setup is evaluated.
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

    # Entry hierarchy: POI retest is preferred; otherwise use the confirmed
    # structure-reclaim close. This is materially less restrictive than the
    # original all-filters stack without accepting a pre-structure signal.
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

    # Prefer the nearest valid draw-on-liquidity target. If none exists,
    # preserve the hybrid's structural 2R fallback.
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
        "displacement_confirmed": True,
        "entry_trigger": trigger,
        "premium_discount_zone": "not_required",
        "timestamp": candles_1h[-1]["time"],
    }
