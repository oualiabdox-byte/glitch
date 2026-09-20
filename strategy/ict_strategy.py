"""Strict ICT 2022 Forex strategy.

Decision tree:
4H bias -> DOL -> 1H liquidity sweep -> MSS -> displacement/FVG
-> premium/discount -> session -> retest -> structural stop -> R:R.

All decisions use closed candles supplied by the caller. No broker/execution logic
belongs in this module.
"""

from . import market_structure, liquidity, ict_bias, displacement, fvg, sessions


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
    # JPY-quoted FX pairs conventionally use 0.01; most others use 0.0001.
    return 0.01 if "JPY" in pair.upper() else 0.0001


def _find_recent_sweep(candles, bias, lookback=12, reference_bars=6):
    """Return the latest valid sweep, excluding the current confirmation candle."""
    if len(candles) < reference_bars + 3:
        return None
    start = max(0, len(candles) - lookback - 1)
    end = len(candles) - 1
    for i in range(end - 1, start - 1, -1):
        before = candles[max(0, i - reference_bars):i]
        if not before:
            continue
        c = candles[i]
        if bias == "LONG":
            level = min(x["low"] for x in before)
            if c["low"] < level and c["close"] > level:
                return {"time": c["time"], "level": level, "extreme": c["low"]}
        else:
            level = max(x["high"] for x in before)
            if c["high"] > level and c["close"] < level:
                return {"time": c["time"], "level": level, "extreme": c["high"]}
    return None


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
    """Return a setup dict only when every strict condition is satisfied.

    The caller must provide closed 1H/4H candles. Entry is an FVG zone and
    execution/retest handling is deliberately left to the backtest/execution
    layer.
    """
    if len(candles_1h) < 30 or len(candles_4h) < 30:
        return None

    bias = ict_bias.htf_bias_4h(candles_4h)
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

    # Draw on liquidity: nearest valid target in the trade direction.
    target_pool = min(
        directional,
        key=lambda p: abs(p["price"] - current)
    )

    recent_1h = candles_1h[-48:]
    sweep = _find_recent_sweep(recent_1h, bias)
    if not sweep:
        return None

    # MSS must occur after the sweep, not before it.
    sweep_idx = next(
        (i for i, c in enumerate(recent_1h) if c["time"] == sweep["time"]),
        None,
    )
    if sweep_idx is None or sweep_idx < 6 or sweep_idx >= len(recent_1h) - 1:
        return None

    pre = recent_1h[:sweep_idx + 1]
    post = recent_1h[sweep_idx + 1:]
    if bias == "LONG":
        swings = market_structure.find_swing_highs(pre)
        if not swings or not any(c["close"] > swings[-1]["high"] for c in post):
            return None
    else:
        swings = market_structure.find_swing_lows(pre)
        if not swings or not any(c["close"] < swings[-1]["low"] for c in post):
            return None

    fvg_result = fvg.find_fvg(
        recent_1h,
        min_gap_atr=min_fvg_atr,
        required_side=bias,
        displacement_min_atr=min_displacement_atr,
    )
    if not fvg_result:
        return None

    # Do not accept an FVG that was formed before the sweep/MSS sequence.
    if fvg_result["creator_idx"] <= sweep_idx:
        return None

    creator_idx = fvg_result["creator_idx"]
    if not displacement.is_displaced(
        recent_1h[:creator_idx + 1],
        creator_idx,
        min_body_atr_ratio=min_displacement_atr,
    ):
        return None

    # 4H premium/discount. LONG must be discount; SHORT must be premium.
    dealing = candles_4h[-6:]
    dealing_low = min(c["low"] for c in dealing)
    dealing_high = max(c["high"] for c in dealing)
    dr = dealing_high - dealing_low
    if dr <= 0:
        return None
    position = (current - dealing_low) / dr
    if bias == "LONG" and position >= 0.50:
        return None
    if bias == "SHORT" and position <= 0.50:
        return None

    # Structural stop: beyond the actual sweep extreme plus a small ATR buffer.
    atr = _atr(recent_1h, 14)
    if atr <= 0:
        return None
    buffer = max(atr * stop_atr_buffer, _pip_size(pair) * 1.0)
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
    if rr < min_rr:
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
        "fvg": fvg_result,
        "mss_confirmed": True,
        "displacement_confirmed": True,
        "displacement_atr": min_displacement_atr,
        "fvg_min_atr": min_fvg_atr,
        "premium_discount_zone": "discount" if bias == "LONG" else "premium",
        "timestamp": candles_1h[-1]["time"],
    }
