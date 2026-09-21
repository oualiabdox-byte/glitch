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
from . import ict_bias, market_structure, liquidity, fvg, displacement, order_blocks, dominating_candle, breaker_blocks, ote, mitigation, smc_engine


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



def _abc_reversal_confirmation(recent, sweep_idx, side, swing_length=3):
    """Confirm the public DaviddTech-style ABC reversal structure causally.

    LONG:
      H0 -> LL1 -> H1 (break above H0) -> FOMO LL2 -> close above LL1.
    SHORT:
      L0 -> HH1 -> L1 (break below L0) -> FOMO HH2 -> close below HH1.

    Only swings confirmed inside candles available before the current candle are
    used. The current candle is used only for the final break confirmation.
    """
    if sweep_idx is None or sweep_idx < 2 or len(recent) < swing_length * 2 + 5:
        return None

    # The pattern must form after the liquidity sweep. Keep the current candle
    # out of pivot detection so the helper cannot look into the future.
    history = recent[: -1]
    if sweep_idx >= len(history) - 1:
        return None

    if side == "LONG":
        highs = market_structure.find_swing_highs(history, length=swing_length)
        lows = market_structure.find_swing_lows(history, length=swing_length)
        if not highs or not lows:
            return None

        highs = sorted(highs, key=lambda x: x["idx"])
        lows = sorted(lows, key=lambda x: x["idx"])

        # H0 -> LL1
        for h0 in reversed(highs):
            if h0["idx"] <= sweep_idx:
                continue
            ll1_candidates = [
                x for x in lows
                if x["idx"] > h0["idx"] and x["low"] < h0["high"]
            ]
            if not ll1_candidates:
                continue
            ll1 = ll1_candidates[0]

            # H1 must break H0.
            h1_candidates = [
                x for x in highs
                if x["idx"] > ll1["idx"] and x["high"] > h0["high"]
            ]
            if not h1_candidates:
                continue
            h1 = h1_candidates[0]

            # FOMO LL2 must be lower than LL1.
            fomo_candidates = [
                x for x in lows
                if x["idx"] > h1["idx"] and x["low"] < ll1["low"]
            ]
            if not fomo_candidates:
                continue
            fomo = fomo_candidates[0]

            # Final confirmation: current closed candle breaks previous LL1.
            if recent[-1]["close"] > ll1["low"]:
                return {
                    "confirmed": True,
                    "pattern": "H_LL_H_FOMO_LL_BREAK",
                    "origin": h0,
                    "previous_ll": ll1,
                    "break_high": h1,
                    "fomo_extreme": fomo,
                    "break_level": ll1["low"],
                }

    else:
        lows = market_structure.find_swing_lows(history, length=swing_length)
        highs = market_structure.find_swing_highs(history, length=swing_length)
        if not lows or not highs:
            return None

        lows = sorted(lows, key=lambda x: x["idx"])
        highs = sorted(highs, key=lambda x: x["idx"])

        # L0 -> HH1
        for l0 in reversed(lows):
            if l0["idx"] <= sweep_idx:
                continue
            hh1_candidates = [
                x for x in highs
                if x["idx"] > l0["idx"] and x["high"] > l0["low"]
            ]
            if not hh1_candidates:
                continue
            hh1 = hh1_candidates[0]

            # L1 must break L0.
            l1_candidates = [
                x for x in lows
                if x["idx"] > hh1["idx"] and x["low"] < l0["low"]
            ]
            if not l1_candidates:
                continue
            l1 = l1_candidates[0]

            # FOMO HH2 must be higher than HH1.
            fomo_candidates = [
                x for x in highs
                if x["idx"] > l1["idx"] and x["high"] > hh1["high"]
            ]
            if not fomo_candidates:
                continue
            fomo = fomo_candidates[0]

            # Final confirmation: current closed candle breaks previous HH1.
            if recent[-1]["close"] < hh1["high"]:
                return {
                    "confirmed": True,
                    "pattern": "L_HH_L_FOMO_HH_BREAK",
                    "origin": l0,
                    "previous_hh": hh1,
                    "break_low": l1,
                    "fomo_extreme": fomo,
                    "break_level": hh1["high"],
                }

    return None


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
    enable_breaker=True,
    enable_ote=True,
    enable_mitigation=True,
    min_confluence=0,
    entry_model="auto",
):
    """Calibrated SMC entry model.

    Shared context:
      1. 4H directional bias
      2. causal SMC facts from local detectors and optional pyvsmc

    Independent entry models:
      - REVERSAL: premium/discount + liquidity sweep/inducement
      - CONTINUATION: HTF bias + fresh FVG retest
      - EXPANSION: displacement + confirmed post-event structure

    SMC context:
      FVG, OB, breaker, OTE and mitigation are descriptive confluence.
      They are not an all-filters stack.
    """
    if len(candles_1h) < 30 or len(candles_4h) < 30:
        return None

    bias = ict_bias.htf_bias_4h(candles_4h)
    if bias not in ("LONG", "SHORT"):
        return None

    if require_session and session_context not in ("london", "new_york", "overlap"):
        return None

    recent = candles_1h[-48:]

    # Independent entry paths: reversal, continuation, expansion.
    if entry_model not in ("auto", "reversal", "continuation", "expansion"):
        raise ValueError("invalid entry_model")

    dealing = candles_4h[-6:]
    dealing_low = min(c["low"] for c in dealing)
    dealing_high = max(c["high"] for c in dealing)
    dealing_range = dealing_high - dealing_low
    if dealing_range <= 0:
        return None
    pd_position = (recent[-1]["close"] - dealing_low) / dealing_range
    pd_aligned = (
        (bias == "LONG" and pd_position < 0.50)
        or (bias == "SHORT" and pd_position > 0.50)
    )

    sweep = _find_recent_sweep(recent, bias, lookback=16, reference_bars=5)
    abc = None
    if sweep and pd_aligned and entry_model in ("auto", "reversal"):
        sweep_idx = next((i for i, c in enumerate(recent) if c["time"] == sweep["time"]), None)
        abc = _abc_reversal_confirmation(recent, sweep_idx, bias, swing_length=3)
    model = "reversal" if abc and abc["confirmed"] else None

    # Continuation does not require a sweep or MSS: HTF bias + fresh FVG retest.
    if model is None and entry_model in ("auto", "continuation"):
        candidate_fvg = fvg.find_fvg(
            recent,
            min_gap_atr=min_fvg_atr,
            required_side=bias,
            displacement_min_atr=min_displacement_atr,
        )
        if candidate_fvg and _fvg_retested(recent, candidate_fvg, bias):
            model = "continuation"


    event_idx = None
    event_type = None
    if sweep and model != "continuation":
        event_idx = next(
            (i for i, c in enumerate(recent) if c["time"] == sweep["time"]),
            None,
        )
        event_type = "LIQUIDITY_SWEEP"

    # A clean directional displacement can initiate the sequence when no
    # recent liquidity sweep is present.
    if event_idx is None and model is None:
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

    if model is None and event_idx is not None:
        model = "expansion"
    if model is None:
        return None

    mss = False
    mss_level = None
    break_idx = None
    if model == "expansion":
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
    if fvg_result and event_idx is not None and fvg_result["creator_idx"] <= event_idx and model == "expansion":
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
        trigger = "EVENT_CONFIRMATION"

    atr = _atr(recent, 14)
    if atr <= 0:
        return None

    if abc and model == "reversal":
        extreme = abc["fomo_extreme"]["low"] if bias == "LONG" else abc["fomo_extreme"]["high"]
    elif event_idx is not None:
        post = recent[event_idx + 1:]
        if not post:
            return None
        extreme = min(c["low"] for c in post[-5:]) if bias == "LONG" else max(c["high"] for c in post[-5:])
    elif fvg_result:
        extreme = fvg_result["bottom"] if bias == "LONG" else fvg_result["top"]
    else:
        extreme = recent[-1]["low"] if bias == "LONG" else recent[-1]["high"]

    buffer = max(atr * stop_atr_buffer, _pip_size(pair))
    stop = extreme - buffer if bias == "LONG" else extreme + buffer

    context = _confluence_context(
        candles_1h, candles_4h, bias, recent[-1]["close"], session_context
    )
    # pyvsmc is optional detector data only; it never becomes a hard gate.
    context["smc_engine"] = smc_engine.analyze(recent)

    # Dominating Candle is a non-blocking structural confluence. The source
    # logic is range-containment, not a classic two-candle engulfing pattern.
    dc_context = dominating_candle.dc_context(
        recent, min_contained=dc_min_contained, lookback=dc_lookback
    )
    dc = dc_context["dc"]
    dc_break = dc_context["dc_breakout"]
    dc_aligned = bool(dc_break and dc_break == bias)

    breaker = None
    if enable_breaker and ob_result:
        breaker = breaker_blocks.find_breaker_block(
            recent, ob_result, bias, break_idx=break_idx
        )

    ote_zone = None
    ote_aligned = False
    if enable_ote and event_idx is not None:
        impulse = recent[event_idx:(break_idx + 1) if break_idx is not None else len(recent)]
        if impulse:
            impulse_low = min(c["low"] for c in impulse)
            impulse_high = max(c["high"] for c in impulse)
            ote_zone = ote.compute_ote(impulse_low, impulse_high, bias)
            ote_aligned = ote.price_in_ote(recent[-1]["close"], ote_zone)

    mitigation_fresh = True
    if enable_mitigation and ob_result:
        mitigation_fresh = not mitigation.zone_mitigated(recent, ob_result, bias)
    if enable_mitigation and fvg_result:
        mitigation_fresh = mitigation_fresh and not mitigation.zone_mitigated(
            recent, fvg_result, bias
        )
    mitigation_confluence = bool(
        enable_mitigation and (ob_result or fvg_result) and mitigation_fresh
    )

    # Add DC to the descriptive confluence score only. It is deliberately
    # NOT a mandatory gate, preventing the SMC stack from collapsing to zero
    # trades on sparse historical samples.
    if dc_aligned:
        context["confluence_score"] += 1
    context["confluence_max"] = 4
    if breaker:
        context["confluence_score"] += 1
    if ote_aligned:
        context["confluence_score"] += 1
    if mitigation_confluence:
        context["confluence_score"] += 1

    context["confluence_max"] = 4 + int(enable_breaker) + int(enable_ote) + int(enable_mitigation)
    context["advanced_confluence"] = {
        "breaker_valid": bool(breaker),
        "ote_valid": bool(ote_zone),
        "ote_aligned": ote_aligned,
        "mitigation_fresh": mitigation_fresh,
        "mitigation_confluence": mitigation_confluence,
        "enabled": {
            "breaker": enable_breaker,
            "ote": enable_ote,
            "mitigation": enable_mitigation,
        },
    }
    context.update({
        "dc_valid": bool(dc),
        "dc_breakout": dc_break,
        "dc_aligned": dc_aligned,
        "dc_low": dc["low"] if dc else None,
        "dc_high": dc["high"] if dc else None,
        "dc_time": dc["time"] if dc else None,
        "dc_contained_bars": dc["contained_bars"] if dc else 0,
        "breaker_block": breaker,
        "ote_zone": ote_zone,
        "ote_aligned": ote_aligned,
        "mitigation_fresh": mitigation_fresh,
        "mitigation_confluence": mitigation_confluence,
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
    if context["confluence_score"] < min_confluence:
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
        "mss_confirmed": bool(mss),
        "mss_level": mss_level,
        "mss_break_idx": break_idx,
        "entry_model": model,
        "event_type": event_type,
        "abc_confirmed": bool(abc and abc["confirmed"]),
        "abc_pattern": abc["pattern"] if abc else None,
        "abc_break_level": abc["break_level"] if abc else None,
        "abc_fomo_extreme": (abc["fomo_extreme"]["low"] if bias == "LONG" else abc["fomo_extreme"]["high"]) if abc else None,
        "displacement_confirmed": event_type == "DISPLACEMENT" or (
            fvg_result is not None
        ),
        "entry_trigger": trigger,
        **context,
        "timestamp": candles_1h[-1]["time"],
    }
