"""Strict, broker-agnostic ICT/SMC setup engine.

Decision tree:
4H structure -> DOL -> 1H liquidity sweep -> post-sweep MSS ->
displacement -> FVG -> reaction/retest -> 4H dealing range ->
premium/discount -> session -> structural stop -> R:R.

No arbitrary confidence score is used. The result contains auditable
evidence and hard-gate diagnostics.
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


def _find_recent_sweep(candles, bias, lookback=12, reference_bars=6,
                       mode="structure", swing_length=3,
                       tolerance_atr=0.10, valid_window_bars=6):
    if len(candles) < reference_bars + 3:
        return None
    if mode not in ("structure", "legacy"):
        raise ValueError("invalid sweep mode")
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

        if mode == "structure":
            pre = candles[:i]
            if bias == "LONG":
                swings = market_structure.find_swing_lows(pre, length=swing_length)
                if not swings:
                    continue
                level = swings[-1]["low"]
                penetration = level - c["low"]
                if penetration >= atr * tolerance_atr and c["low"] < level and c["close"] > level:
                    return {
                        "time": c["time"], "level": level, "extreme": c["low"],
                        "source": "SWING_LOW",
                        "penetration_atr": penetration / atr if atr > 0 else 0.0,
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
                        "time": c["time"], "level": level, "extreme": c["high"],
                        "source": "SWING_HIGH",
                        "penetration_atr": penetration / atr if atr > 0 else 0.0,
                        "age_bars": age,
                    }
            continue

        before = candles[max(0, i - reference_bars):i]
        if not before:
            continue
        if bias == "LONG":
            level = min(x["low"] for x in before)
            penetration = level - c["low"]
            if penetration >= atr * tolerance_atr and c["low"] < level and c["close"] > level:
                return {"time": c["time"], "level": level, "extreme": c["low"],
                        "source": "ROLLING_LOW",
                        "penetration_atr": penetration / atr if atr > 0 else 0.0,
                        "age_bars": age}
        else:
            level = max(x["high"] for x in before)
            penetration = c["high"] - level
            if penetration >= atr * tolerance_atr and c["high"] > level and c["close"] < level:
                return {"time": c["time"], "level": level, "extreme": c["high"],
                        "source": "ROLLING_HIGH",
                        "penetration_atr": penetration / atr if atr > 0 else 0.0,
                        "age_bars": age}
    return None


def _mss_after_sweep(candles, bias, sweep_idx, swing_length=3):
    if sweep_idx < swing_length or sweep_idx >= len(candles) - 1:
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
    min_displacement_atr=1.25,
    min_fvg_atr=0.10,
    stop_atr_buffer=0.10,
    min_rr=2.0,
):
    if len(candles_1h) < 30 or len(candles_4h) < 30:
        return None

    htf = ict_bias.htf_context_4h(candles_4h, swing_length=3)
    bias = htf.get("bias")
    if bias not in ("LONG", "SHORT"):
        return None

    sess = session_context or sessions.current_session()
    if sess not in ("london", "new_york", "overlap"):
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
        recent_1h, bias, mode="structure", swing_length=3,
        tolerance_atr=0.10, valid_window_bars=6,
    )
    if not sweep:
        return None

    sweep_idx = next(
        (i for i, c in enumerate(recent_1h) if c["time"] == sweep["time"]), None
    )
    mss_ok, mss_level = _mss_after_sweep(recent_1h, bias, sweep_idx, 3)
    if not mss_ok:
        return None

    fvg_result = fvg.find_fvg(
        recent_1h,
        min_gap_atr=min_fvg_atr,
        required_side=bias,
        displacement_min_atr=min_displacement_atr,
    )
    if not fvg_result or fvg_result["creator_idx"] <= sweep_idx:
        return None

    creator_idx = fvg_result["creator_idx"]
    displacement_ok = displacement.is_displaced(
        recent_1h, creator_idx, min_body_atr_ratio=min_displacement_atr
    )
    if not displacement_ok:
        return None

    current_bar = recent_1h[-1]
    if creator_idx >= len(recent_1h) - 2:
        return None
    if bias == "LONG":
        retest_ok = (
            current_bar["low"] <= fvg_result["top"]
            and current_bar["close"] >= fvg_result["bottom"]
        )
    else:
        retest_ok = (
            current_bar["high"] >= fvg_result["bottom"]
            and current_bar["close"] <= fvg_result["top"]
        )
    if not retest_ok:
        return None

    if bias == "LONG" and htf.get("premium_discount") != "DISCOUNT":
        return None
    if bias == "SHORT" and htf.get("premium_discount") != "PREMIUM":
        return None

    atr = _atr(recent_1h, 14)
    if atr <= 0:
        return None

    ob = order_blocks.find_order_block(recent_1h, fvg_result)
    fib = None
    if htf.get("external_high") is not None and htf.get("external_low") is not None:
        fib = fib_cluster.find_cluster(
            htf["external_high"], htf["external_low"], tolerance=atr * 0.20
        )

    # POI evidence: OB/Fib strengthen the FVG reaction but do not create a trade.
    poi = {
        "fvg": fvg_result,
        "order_block": ob,
        "fib_cluster": fib.get("best") if fib else None,
    }

    buffer = max(atr * stop_atr_buffer, _pip_size(pair))
    entry_mid = (fvg_result["bottom"] + fvg_result["top"]) / 2.0
    if bias == "LONG":
        stop_price = sweep["extreme"] - buffer
        risk_distance = entry_mid - stop_price
        reward_distance = target_pool["price"] - entry_mid
    else:
        stop_price = sweep["extreme"] + buffer
        risk_distance = stop_price - entry_mid
        reward_distance = entry_mid - target_pool["price"]

    if risk_distance <= 0 or reward_distance <= 0:
        return None
    rr = reward_distance / risk_distance

    evidence = setup_analysis.analyze_setup(
        htf=htf, sweep=sweep, mss=mss_level, displacement_ok=displacement_ok,
        fvg=fvg_result, ob=ob, fib=fib, session=sess, rr=rr
    )
    validation = setup_analysis.validate_setup(
        bias=bias, htf=htf, sweep=sweep, mss=mss_level,
        displacement_ok=displacement_ok, fvg=fvg_result,
        session=sess, rr=rr, min_rr=min_rr
    )
    if not validation["valid"]:
        return None

    return {
        "pair": pair,
        "side": bias,
        "entry_zone": (fvg_result["bottom"], fvg_result["top"]),
        "entry_mid": entry_mid,
        "stop_price": stop_price,
        "stop_ref": sweep["extreme"],
        "tp_target": target_pool["price"],
        "target_source": target_pool["source"],
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
        "premium_discount_zone": "discount" if bias == "LONG" else "premium",
        "evidence": evidence,
        "timestamp": candles_1h[-1]["time"],
    }
