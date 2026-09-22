"""Strict, broker-agnostic ICT/SMC setup engine.

Decision tree:
4H structure -> DOL -> 1H liquidity sweep -> post-sweep MSS ->
displacement -> FVG -> reaction/retest -> 4H dealing range ->
premium/discount -> session -> structural stop -> R:R.

There is one active setup path. No legacy trigger modes or arbitrary
confidence score are retained.
"""

from . import (
    market_structure,
    liquidity,
    ict_bias,
    displacement,
    fvg,
    order_blocks,
    sessions,
    fib_cluster,
    setup_analysis,
    breakout_retest,
    structure_entry,
)


def _atr(candles, period=14):
    if len(candles) < 2:
        return 0.0
    start = max(1, len(candles) - period)
    trs = []
    for i in range(start, len(candles)):
        h, l = candles[i]["high"], candles[i]["low"]
        pc = candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else 0.0


def _pip_size(pair):
    return 0.01 if "JPY" in pair.upper() else 0.0001


def _find_recent_sweep(candles, bias, lookback=12, swing_length=3,
                       tolerance_atr=0.10, valid_window_bars=6):
    if len(candles) < swing_length + 3:
        return None
    if swing_length < 2:
        raise ValueError("swing_length must be >= 2")
    if tolerance_atr < 0 or valid_window_bars < 1:
        raise ValueError("invalid sweep tolerance/window")

    start = max(0, len(candles) - lookback - 1)
    end = len(candles) - 1

    for i in range(end - 1, start - 1, -1):
        age = end - i
        if age > valid_window_bars:
            continue

        c = candles[i]
        atr = _atr(candles[:i + 1], period=14)
        if atr <= 0:
            continue

        pre = candles[:i]
        if bias == "LONG":
            swings = market_structure.find_swing_lows(pre, length=swing_length)
            if not swings:
                continue
            level = swings[-1]["low"]
            penetration = level - c["low"]
            if penetration >= atr * tolerance_atr and c["low"] < level and c["close"] > level:
                return {
                    "time": c["time"],
                    "level": level,
                    "extreme": c["low"],
                    "source": "SWING_LOW",
                    "penetration_atr": penetration / atr,
                    "age_bars": age,
                }
        else:
            swings = market_structure.find_swing_highs(pre, length=swing_length)
            if not swings:
                continue
            level = swings[-1]["high"]
            penetration = c["high"] - level
            if penetration >= atr * tolerance_atr and c["high"] > level and c["close"] < level:
                return {
                    "time": c["time"],
                    "level": level,
                    "extreme": c["high"],
                    "source": "SWING_HIGH",
                    "penetration_atr": penetration / atr,
                    "age_bars": age,
                }
    return None


def _mss_after_sweep(candles, bias, sweep_idx, swing_length=3):
    if sweep_idx is None or sweep_idx < swing_length or sweep_idx >= len(candles) - 1:
        return False, None
    pre = candles[:sweep_idx + 1]
    post = candles[sweep_idx + 1:]

    if bias == "LONG":
        swings = market_structure.find_swing_highs(pre, swing_length)
        if not swings:
            return False, None
        level = swings[-1]["high"]
        for c in post:
            if c["close"] > level:
                return True, level
    else:
        swings = market_structure.find_swing_lows(pre, swing_length)
        if not swings:
            return False, None
        level = swings[-1]["low"]
        for c in post:
            if c["close"] < level:
                return True, level
    return False, None


def evaluate_ict_2022(
    candles_1h,
    candles_4h,
    pair,
    session_context="london",
    min_displacement_atr=0.75,
    min_fvg_atr=0.0,
    stop_atr_buffer=0.10,
    min_rr=1.5,
    swing_length=3,
    require_fresh_fvg_retest=False,
    fvg_retest_tolerance_atr=0.15,
    fvg_retest_max_wait_bars=6,
    allow_fixed_rr_fallback=True,
    require_sweep=True,
    require_mss=True,
    require_displacement=True,
    require_fvg=True,
    require_order_block=False,
    require_session=True,
    require_premium_discount=True,
    require_min_rr=True,
):
    if len(candles_1h) < 30 or len(candles_4h) < 30:
        return None

    if swing_length < 2:
        raise ValueError("swing_length must be >= 2")
    htf = ict_bias.htf_context_4h(candles_4h, swing_length=swing_length)
    bias = htf.get("bias")
    if bias not in ("LONG", "SHORT"):
        return None

    sess = session_context or sessions.current_session()
    if require_session and sess not in ("london", "new_york", "overlap"):
        return None

    pools = liquidity.liquidity_pools(candles_4h[-30:])
    if not pools:
        return None

    current = candles_1h[-1]["close"]
    directional = [
        p for p in pools
        if (bias == "LONG" and p["type"] == "resistance" and p["price"] > current)
        or (bias == "SHORT" and p["type"] == "support" and p["price"] < current)
    ]
    if not directional:
        return None
    target_pool = min(directional, key=lambda p: abs(p["price"] - current))

    recent_1h = candles_1h[-48:]
    sweep = _find_recent_sweep(
        recent_1h,
        bias,
        swing_length=swing_length,
        tolerance_atr=0.10,
        valid_window_bars=6,
    )
    if require_sweep and not sweep:
        return None

    sweep_idx = (
        next((i for i, c in enumerate(recent_1h) if c["time"] == sweep["time"]), None)
        if sweep else None
    )
    mss_ok, mss_level = _mss_after_sweep(recent_1h, bias, sweep_idx, swing_length)
    if require_mss and not mss_ok:
        return None

    fvg_result = fvg.find_fvg(
        recent_1h,
        min_gap_atr=min_fvg_atr,
        required_side=bias,
        displacement_min_atr=min_displacement_atr,
    )
    if require_fvg and (not fvg_result or fvg_result["creator_idx"] <= (sweep_idx if sweep_idx is not None else -1)):
        return None

    creator_idx = fvg_result["creator_idx"] if fvg_result else None
    displacement_ok = bool(
        fvg_result and displacement.is_displaced(
            recent_1h,
            creator_idx,
            min_body_atr_ratio=min_displacement_atr,
        )
    )
    if require_displacement and not displacement_ok:
        return None

    retest_atr = _atr(recent_1h, 14)
    if not fvg_result:
        retest_ok = False
    elif require_fresh_fvg_retest:
        retest_ok = fvg.is_fresh_retest(recent_1h, fvg_result)
    else:
        retest_ok = fvg.is_near_or_continuation_retest(
            recent_1h,
            fvg_result,
            tolerance=retest_atr * fvg_retest_tolerance_atr,
            max_wait_bars=fvg_retest_max_wait_bars,
        )
    if require_fvg and not retest_ok:
        return None

    if require_premium_discount and bias == "LONG" and htf.get("premium_discount") != "DISCOUNT":
        return None
    if require_premium_discount and bias == "SHORT" and htf.get("premium_discount") != "PREMIUM":
        return None

    atr = _atr(recent_1h, 14)
    if atr <= 0:
        return None

    ob = order_blocks.find_order_block(recent_1h, fvg_result) if fvg_result else None
    if require_order_block and not ob:
        return None
    fib = None
    if htf.get("external_high") is not None and htf.get("external_low") is not None:
        fib = fib_cluster.find_cluster(
            htf["external_high"],
            htf["external_low"],
            tolerance=atr * 0.20,
        )

    poi = {
        "fvg": fvg_result,
        "order_block": ob,
        "fib_cluster": fib.get("best") if fib else None,
    }

    buffer = max(atr * stop_atr_buffer, _pip_size(pair))
    entry_mid = (
        (fvg_result["bottom"] + fvg_result["top"]) / 2.0
        if fvg_result else recent_1h[-1]["close"]
    )
    if bias == "LONG":
        stop_price = (sweep["extreme"] if sweep else recent_1h[-1]["low"]) - buffer
        risk_distance = entry_mid - stop_price
        reward_distance = target_pool["price"] - entry_mid
    else:
        stop_price = (sweep["extreme"] if sweep else recent_1h[-1]["high"]) + buffer
        risk_distance = stop_price - entry_mid
        reward_distance = entry_mid - target_pool["price"]

    if risk_distance <= 0 or reward_distance <= 0:
        return None
    rr = reward_distance / risk_distance

    if rr + 1e-9 < min_rr and allow_fixed_rr_fallback and require_min_rr:
        target_price = (
            entry_mid + risk_distance * min_rr
            if bias == "LONG"
            else entry_mid - risk_distance * min_rr
        )
        target_source = "FIXED_RR_FALLBACK"
        reward_distance = abs(target_price - entry_mid)
        rr = reward_distance / risk_distance
    else:
        target_price = target_pool["price"]
        target_source = target_pool["source"]

    evidence = setup_analysis.analyze_setup(
        htf=htf,
        sweep=sweep,
        mss=mss_level,
        displacement_ok=displacement_ok,
        fvg=fvg_result,
        ob=ob,
        fib=fib,
        session=sess,
        rr=rr,
    )
    validation = setup_analysis.validate_setup(
        bias=bias,
        htf=htf,
        sweep=sweep,
        mss=mss_level,
        displacement_ok=displacement_ok,
        fvg=fvg_result,
        session=sess,
        rr=rr,
        min_rr=min_rr,
        require_sweep=require_sweep,
        require_mss=require_mss,
        require_displacement=require_displacement,
        require_fvg=require_fvg,
        require_session=require_session,
        require_premium_discount=require_premium_discount,
        require_min_rr=require_min_rr,
    )
    if not validation["valid"]:
        return None

    return {
        "pair": pair,
        "side": bias,
        "entry_zone": (
            (fvg_result["bottom"], fvg_result["top"])
            if fvg_result else (entry_mid, entry_mid)
        ),
        "entry_mid": entry_mid,
        "stop_price": stop_price,
        "stop_ref": sweep["extreme"] if sweep else None,
        "tp_target": target_price,
        "target_source": target_source,
        "rr": rr,
        "bias": bias,
        "session": sess,
        "htf_context": htf,
        "sweep": sweep,
        "mss_level": mss_level,
        "poi": poi,
        "fvg": fvg_result,
        "mss_confirmed": True,
        "displacement_confirmed": True,
        "displacement_atr": min_displacement_atr,
        "fvg_min_atr": min_fvg_atr,
        "fvg_retest_mode": "fresh" if require_fresh_fvg_retest else "near_or_continuation",
        "premium_discount_zone": "discount" if bias == "LONG" else "premium",
        "evidence": evidence,
        "timestamp": candles_1h[-1]["time"],
    }


def evaluate_breakout_retest(
    candles_1h,
    candles_4h,
    pair,
    session_context="london",
    stop_atr_buffer=0.10,
    min_rr=1.5,
    swing_length=3,
    breakout_body_atr=0.50,
    retest_window=6,
    allow_fixed_rr_fallback=True,
    require_target_pool=False,
    require_min_rr=True,
):
    """Evaluate the causal breakout/retest entry path.

    This is deliberately a separate path so the original ICT/FVG engine can
    be compared against it without changing its historical behavior.
    """
    if len(candles_1h) < 30 or len(candles_4h) < 30:
        return None
    if swing_length < 2:
        raise ValueError("swing_length must be >= 2")

    htf = ict_bias.htf_context_4h(candles_4h, swing_length=swing_length)
    bias = htf.get("bias")
    sess = session_context or sessions.current_session()
    if bias not in ("LONG", "SHORT"):
        return None
    session_preferred = sess in ("london", "new_york", "overlap")

    pools = liquidity.liquidity_pools(candles_4h[-30:])
    current = candles_1h[-1]["close"]
    directional = [
        p for p in pools
        if (bias == "LONG" and p["type"] == "resistance" and p["price"] > current)
        or (bias == "SHORT" and p["type"] == "support" and p["price"] < current)
    ]
    target_pool = min(directional, key=lambda p: abs(p["price"] - current)) if directional else None
    if require_target_pool and target_pool is None:
        return None

    signal = breakout_retest.find_breakout_retest(
        candles_1h,
        bias,
        end_idx=len(candles_1h) - 1,
        swing_length=swing_length,
        breakout_body_atr=breakout_body_atr,
        retest_window=retest_window,
    )
    if not signal:
        return None

    atr = _atr(candles_1h, 14)
    if atr <= 0:
        return None
    entry_mid = candles_1h[-1]["close"]
    buffer = max(atr * stop_atr_buffer, _pip_size(pair))
    if bias == "LONG":
        stop_price = signal["stop_extreme"] - buffer
        risk_distance = entry_mid - stop_price
    else:
        stop_price = signal["stop_extreme"] + buffer
        risk_distance = stop_price - entry_mid
    if risk_distance <= 0:
        return None
    if target_pool:
        target_price = target_pool["price"]
        target_source = target_pool["source"]
    elif allow_fixed_rr_fallback and not require_target_pool:
        target_price = (
            entry_mid + risk_distance * min_rr
            if bias == "LONG"
            else entry_mid - risk_distance * min_rr
        )
        target_source = "FIXED_RR_FALLBACK"
    else:
        return None
    reward_distance = abs(target_price - entry_mid)
    if reward_distance <= 0:
        return None
    rr = reward_distance / risk_distance
    if require_min_rr and rr + 1e-9 < min_rr:
        return None

    return {
        "pair": pair,
        "side": bias,
        "entry_zone": (signal["level"] - signal["zone_buffer"], signal["level"] + signal["zone_buffer"]),
        "entry_mid": entry_mid,
        "stop_price": stop_price,
        "stop_ref": signal["stop_extreme"],
        "tp_target": target_price,
        "target_source": target_source,
        "rr": rr,
        "bias": bias,
        "session": sess,
        "htf_context": htf,
        "breakout_retest": signal,
        "mss_confirmed": False,
        "displacement_confirmed": True,
        "fvg": None,
        "order_block": None,
        "entry_model": "breakout_retest",
        "evidence": {
            "htf_structure": htf.get("structure"),
            "session_preferred": session_preferred,
            "breakout_close": True,
            "retest_hold": True,
            "follow_through_close": True,
            "breakout_body_atr": signal["breakout_body_atr"],
            "rr": rr,
        },
        "timestamp": candles_1h[-1]["time"],
    }


def evaluate_structure_entry(
    candles_1h,
    candles_4h,
    pair,
    session_context="london",
    stop_atr_buffer=0.10,
    min_rr=1.5,
    swing_length=3,
    allow_fixed_rr_fallback=False,
):
    """Evaluate IDM -> MSS/BOS/CHOCH entry without exact FVG/OB retest."""
    if len(candles_1h) < 30 or len(candles_4h) < 30:
        return None
    if swing_length < 2:
        raise ValueError("swing_length must be >= 2")

    htf = ict_bias.htf_context_4h(candles_4h, swing_length=swing_length)
    bias = htf.get("bias")
    if bias not in ("LONG", "SHORT"):
        return None
    sess = session_context or sessions.current_session()
    session_preferred = sess in ("london", "new_york", "overlap")
    equilibrium = htf.get("equilibrium")
    if equilibrium is None:
        return None

    signal = structure_entry.find_entry(
        candles_1h, bias, end_idx=len(candles_1h) - 1,
        internal_lookback=max(2, swing_length + 1),
    )
    if not signal:
        return None
    entry_mid = candles_1h[-1]["close"]
    # Directional midpoint rule: long in discount, short in premium.
    if bias == "LONG" and entry_mid > equilibrium:
        return None
    if bias == "SHORT" and entry_mid < equilibrium:
        return None

    atr = _atr(candles_1h, 14)
    if atr <= 0:
        return None
    buffer = max(atr * stop_atr_buffer, _pip_size(pair))
    stop_price = (
        signal["stop_extreme"] - buffer
        if bias == "LONG"
        else signal["stop_extreme"] + buffer
    )
    risk_distance = entry_mid - stop_price if bias == "LONG" else stop_price - entry_mid
    if risk_distance <= 0:
        return None
    pools = liquidity.liquidity_pools(candles_4h[-30:])
    directional = [
        p for p in pools
        if (bias == "LONG" and p["type"] == "resistance" and p["price"] > entry_mid)
        or (bias == "SHORT" and p["type"] == "support" and p["price"] < entry_mid)
    ]
    if directional:
        target_pool = min(directional, key=lambda p: abs(p["price"] - entry_mid))
        target_price, target_source = target_pool["price"], target_pool["source"]
    elif allow_fixed_rr_fallback:
        target_price = entry_mid + risk_distance * min_rr if bias == "LONG" else entry_mid - risk_distance * min_rr
        target_source = "FIXED_RR_FALLBACK"
    else:
        return None
    reward_distance = abs(target_price - entry_mid)
    rr = reward_distance / risk_distance
    if rr < min_rr:
        return None

    return {
        "pair": pair, "side": bias, "entry_mid": entry_mid,
        "entry_zone": (signal["break_level"], signal["break_level"]),
        "stop_price": stop_price, "stop_ref": signal["stop_extreme"],
        "tp_target": target_price, "target_source": target_source,
        "rr": rr, "bias": bias, "session": sess,
        "session_preferred": session_preferred, "htf_context": htf,
        "structure_signal": signal, "entry_model": "structure_entry",
        "fvg": None, "order_block": None,
        "premium_discount_zone": "discount" if bias == "LONG" else "premium",
        "evidence": {
            "idm": True, "mss": signal["mss"], "bos": signal["bos"],
            "choch": signal["choch"], "h4_equilibrium": equilibrium,
            "entry_below_or_above_50": True, "session_preferred": session_preferred,
            "path": signal["path"], "rr": rr,
        },
        "timestamp": candles_1h[-1]["time"],
    }
