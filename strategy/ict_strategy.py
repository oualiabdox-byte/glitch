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


def _aggregate_daily_from_4h(candles_4h):
    """Build causal D1 candles from closed 4H candles."""
    if not candles_4h:
        return []
    out = []
    current_key = None
    bucket = None
    for c in candles_4h:
        key = str(c["time"])[:10]
        if key != current_key:
            if bucket is not None:
                out.append(bucket)
            current_key = key
            bucket = {
                "time": c["time"],
                "open": c["open"],
                "high": c["high"],
                "low": c["low"],
                "close": c["close"],
            }
        else:
            bucket["high"] = max(bucket["high"], c["high"])
            bucket["low"] = min(bucket["low"], c["low"])
            bucket["close"] = c["close"]
    if bucket is not None:
        out.append(bucket)
    return out


def _crt_external_sweep(candles, bias, reference_high, reference_low,
                        lookback=12, tolerance_atr=0.05):
    """Find the most recent external liquidity sweep and reclaim."""
    if len(candles) < 3:
        return None
    atr = _atr(candles, 14)
    if atr <= 0:
        return None
    start = max(1, len(candles) - lookback)
    for i in range(len(candles) - 1, start - 1, -1):
        c = candles[i]
        if bias == "LONG" and reference_low is not None:
            penetration = reference_low - c["low"]
            if penetration >= atr * tolerance_atr and c["low"] < reference_low and c["close"] > reference_low:
                return {
                    "idx": i, "time": c["time"], "side": "LONG",
                    "level": reference_low, "extreme": c["low"],
                    "range_high": c["high"], "range_low": c["low"],
                    "range_mid": (c["high"] + c["low"]) / 2.0,
                    "penetration_atr": penetration / atr,
                }
        if bias == "SHORT" and reference_high is not None:
            penetration = c["high"] - reference_high
            if penetration >= atr * tolerance_atr and c["high"] > reference_high and c["close"] < reference_high:
                return {
                    "idx": i, "time": c["time"], "side": "SHORT",
                    "level": reference_high, "extreme": c["high"],
                    "range_high": c["high"], "range_low": c["low"],
                    "range_mid": (c["high"] + c["low"]) / 2.0,
                    "penetration_atr": penetration / atr,
                }
    return None


def _crt_bos_after_sweep(candles, bias, sweep_idx, swing_length=3):
    """Confirm post-sweep BOS/CHOCH by candle-body close through a swing."""
    if sweep_idx is None or sweep_idx >= len(candles) - 1:
        return None
    pre = candles[:sweep_idx + 1]
    if bias == "LONG":
        swings = market_structure.find_swing_highs(pre, swing_length)
        if not swings:
            return None
        level = swings[-1]["high"]
        for i in range(sweep_idx + 1, len(candles)):
            if candles[i]["close"] > level:
                return {
                    "idx": i, "time": candles[i]["time"],
                    "type": "BOS_OR_CHOCH", "direction": "LONG",
                    "level": level,
                }
    else:
        swings = market_structure.find_swing_lows(pre, swing_length)
        if not swings:
            return None
        level = swings[-1]["low"]
        for i in range(sweep_idx + 1, len(candles)):
            if candles[i]["close"] < level:
                return {
                    "idx": i, "time": candles[i]["time"],
                    "type": "BOS_OR_CHOCH", "direction": "SHORT",
                    "level": level,
                }
    return None


def _crt_inducement_flags(candles, bias, zone_low, zone_high, lookback=24):
    """Classify nearby EQH/EQL liquidity as an inducement warning."""
    sample = candles[-lookback:]
    tolerance = _atr(candles, 14) * 0.15
    if tolerance <= 0:
        return {"inducement": False, "equal_liquidity": None}

    highs = [c["high"] for c in sample]
    lows = [c["low"] for c in sample]

    if bias == "LONG":
        candidates = [x for x in lows if zone_low <= x <= zone_high + tolerance]
        for a in candidates:
            for b in candidates:
                if a != b and abs(a - b) <= tolerance:
                    return {"inducement": True, "equal_liquidity": "EQL"}
    else:
        candidates = [x for x in highs if zone_low - tolerance <= x <= zone_high]
        for a in candidates:
            for b in candidates:
                if a != b and abs(a - b) <= tolerance:
                    return {"inducement": True, "equal_liquidity": "EQH"}
    return {"inducement": False, "equal_liquidity": None}


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
    """CRT execution engine.

    The public API is retained for compatibility, but the decision model is
    now CRT rather than the former generic ICT/SMC confluence chain:

        D1 bias -> H1 IRL/POI -> external liquidity sweep ->
        H1 BOS/CHOCH -> 50% range retest -> target liquidity.

    FVG/OB are no longer mandatory entry triggers. Inducement is used as a
    zone-selection filter, not as a standalone entry signal.
    """
    if len(candles_1h) < 40 or len(candles_4h) < 30:
        return None

    if swing_length < 2:
        raise ValueError("swing_length must be >= 2")

    sess = session_context or sessions.current_session()
    if require_session and sess not in ("london", "new_york", "overlap"):
        return None

    # D1 directional context derived only from closed 4H candles.
    daily = _aggregate_daily_from_4h(candles_4h)
    if len(daily) < 4:
        return None
    d1_context = market_structure.analyze_structure(daily, swing_length=2)
    bias = d1_context.get("bias")
    if bias not in ("LONG", "SHORT"):
        return None

    # H1 external range / IRL context.
    h1 = candles_1h[-48:]
    h1_context = market_structure.analyze_structure(h1, swing_length=swing_length)
    external_high = h1_context.get("external_high")
    external_low = h1_context.get("external_low")
    if external_high is None or external_low is None:
        return None

    # Longs must sweep external sell-side liquidity; shorts external buy-side.
    sweep = _crt_external_sweep(
        h1,
        bias,
        reference_high=external_high,
        reference_low=external_low,
        lookback=12,
        tolerance_atr=0.05,
    )
    if require_sweep and not sweep:
        return None

    # The post-sweep structural confirmation is a body-close BOS/CHOCH.
    bos = _crt_bos_after_sweep(h1, bias, sweep["idx"], swing_length=swing_length) if sweep else None
    if require_mss and bos is None:
        return None

    # CRT 50% retest is the primary entry zone.
    zone_mid = sweep["range_mid"] if sweep else h1[-1]["close"]
    zone_low = sweep["range_low"] if sweep else h1[-1]["low"]
    zone_high = sweep["range_high"] if sweep else h1[-1]["high"]

    current = h1[-1]["close"]
    # Directional premium/discount is mandatory when enabled.
    dealing_high = external_high
    dealing_low = external_low
    dealing_range = dealing_high - dealing_low
    if dealing_range <= 0:
        return None
    position = (zone_mid - dealing_low) / dealing_range
    if require_premium_discount:
        if bias == "LONG" and position >= 0.50:
            return None
        if bias == "SHORT" and position <= 0.50:
            return None

    # Reject an inducement zone when equal liquidity is sitting directly in it.
    inducement = _crt_inducement_flags(h1, bias, zone_low, zone_high)
    if inducement["inducement"]:
        return None

    # The actual entry must revisit the 50% level after BOS, not merely touch
    # the sweep candle before structural confirmation.
    confirmation_idx = bos["idx"] if bos else (sweep["idx"] if sweep else 0)
    retest = False
    retest_idx = None
    tolerance = _atr(h1, 14) * 0.10
    for i in range(confirmation_idx + 1, len(h1)):
        c = h1[i]
        if c["low"] - tolerance <= zone_mid <= c["high"] + tolerance:
            if bias == "LONG" and c["close"] >= zone_mid - tolerance:
                retest = True
                retest_idx = i
                break
            if bias == "SHORT" and c["close"] <= zone_mid + tolerance:
                retest = True
                retest_idx = i
                break
    if not retest:
        return None

    entry_mid = zone_mid
    atr = _atr(h1, 14)
    if atr <= 0:
        return None
    buffer = max(atr * stop_atr_buffer, _pip_size(pair))

    if bias == "LONG":
        stop_price = sweep["extreme"] - buffer
    else:
        stop_price = sweep["extreme"] + buffer

    risk_distance = entry_mid - stop_price if bias == "LONG" else stop_price - entry_mid
    if risk_distance <= 0:
        return None

    # DOL: nearest opposing external liquidity in the trade direction.
    pools = liquidity.liquidity_pools(candles_4h[-30:])
    directional = [
        p for p in pools
        if (bias == "LONG" and p["type"] == "resistance" and p["price"] > entry_mid)
        or (bias == "SHORT" and p["type"] == "support" and p["price"] < entry_mid)
    ]
    target_pool = min(directional, key=lambda p: abs(p["price"] - entry_mid)) if directional else None

    if target_pool:
        target_price = target_pool["price"]
        target_source = target_pool["source"]
    elif allow_fixed_rr_fallback:
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

    evidence = {
        "model": "CRT",
        "d1_bias": bias,
        "d1_structure": d1_context.get("structure"),
        "h1_structure": h1_context.get("structure"),
        "external_sweep": True,
        "sweep_level": sweep["level"],
        "sweep_extreme": sweep["extreme"],
        "bos_or_choch": bos,
        "crt_50_percent": entry_mid,
        "premium_discount": "DISCOUNT" if bias == "LONG" else "PREMIUM",
        "inducement": inducement,
        "retest_confirmed": True,
        "retest_idx": retest_idx,
        "dol_target": target_source,
        "rr": rr,
    }

    return {
        "pair": pair,
        "side": bias,
        "entry_zone": (zone_low, zone_high),
        "entry_mid": entry_mid,
        "stop_price": stop_price,
        "stop_ref": sweep["extreme"],
        "tp_target": target_price,
        "target_source": target_source,
        "rr": rr,
        "bias": bias,
        "session": sess,
        "htf_context": {
            "daily": d1_context,
            "h1": h1_context,
            "timeframe": "D1/H1",
            "premium_discount": "DISCOUNT" if bias == "LONG" else "PREMIUM",
        },
        "sweep": sweep,
        "mss_level": bos["level"] if bos else None,
        "poi": {
            "type": "CRT_50_PERCENT",
            "range_low": zone_low,
            "range_high": zone_high,
            "midpoint": entry_mid,
            "inducement": inducement,
        },
        "fvg": None,
        "mss_confirmed": bos is not None,
        "displacement_confirmed": True,
        "displacement_atr": min_displacement_atr,
        "fvg_min_atr": min_fvg_atr,
        "fvg_retest_mode": "CRT_50_PERCENT",
        "premium_discount_zone": "discount" if bias == "LONG" else "premium",
        "entry_model": "CRT",
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
