"""Causal H1 structure entry without mandatory FVG/OB touch.

IDM is represented as a closed-bar internal liquidity sweep. MSS is a
post-sweep displacement break. BOS/CHOCH are explicit labels on the same
closed-bar structural break; the labels do not imply institutional causality.
"""
from __future__ import annotations


def _atr(candles, end_idx, period=14):
    if end_idx < 2:
        return 0.0
    start = max(1, end_idx - period)
    trs = []
    for i in range(start, end_idx):
        h, low = candles[i]["high"], candles[i]["low"]
        pc = candles[i - 1]["close"]
        trs.append(max(h - low, abs(h - pc), abs(low - pc)))
    return sum(trs) / len(trs) if trs else 0.0


def find_entry(
    candles,
    side,
    end_idx=None,
    internal_lookback=5,
    sweep_lookback=12,
    sweep_buffer_atr=0.10,
    displacement_atr=0.75,
    max_setup_age=6,
    retest_window=4,
):
    """Find a closed-bar IDM -> MSS/BOS/CHOCH -> confirmation sequence.

    The current bar is used only after it is closed. A returned signal can be
    executed on the following bar. The exact FVG and OB prices are not used.
    """
    if side not in {"LONG", "SHORT"}:
        raise ValueError("side must be LONG or SHORT")
    if internal_lookback < 2 or sweep_lookback < internal_lookback:
        raise ValueError("invalid structure lookbacks")
    last = len(candles) - 1 if end_idx is None else int(end_idx)
    if last >= len(candles):
        raise IndexError("end_idx is outside candle data")
    if last < internal_lookback * 2 + 2:
        return None

    first_sweep = max(internal_lookback, last - sweep_lookback - max_setup_age - 2)
    for sweep_idx in range(last - 2, first_sweep - 1, -1):
        before = candles[max(0, sweep_idx - internal_lookback):sweep_idx]
        if len(before) < internal_lookback:
            continue
        atr = _atr(candles, sweep_idx)
        if atr <= 0:
            continue
        idm = min(c["low"] for c in before) if side == "LONG" else max(c["high"] for c in before)
        sweep = candles[sweep_idx]
        swept = (
            sweep["low"] < idm - atr * sweep_buffer_atr and sweep["close"] >= idm
            if side == "LONG"
            else sweep["high"] > idm + atr * sweep_buffer_atr and sweep["close"] <= idm
        )
        if not swept:
            continue

        break_start = sweep_idx + 1
        break_end = min(last - 1, sweep_idx + max_setup_age)
        for break_idx in range(break_start, break_end + 1):
            preceding = candles[max(sweep_idx + 1, break_idx - internal_lookback):break_idx]
            if len(preceding) < 2:
                continue
            level = max(c["high"] for c in preceding) if side == "LONG" else min(c["low"] for c in preceding)
            breaker = candles[break_idx]
            break_atr = _atr(candles, break_idx)
            body = abs(breaker["close"] - breaker["open"])
            broken = (
                breaker["close"] > level + break_atr * sweep_buffer_atr
                if side == "LONG"
                else breaker["close"] < level - break_atr * sweep_buffer_atr
            )
            if break_atr <= 0 or not broken or body < break_atr * displacement_atr:
                continue

            # A sweep followed by a displacement break is MSS. It is also a
            # BOS of the cached internal level; CHOCH is true when the pre-break
            # local closes show the opposite direction.
            prior = candles[max(0, sweep_idx - internal_lookback):sweep_idx]
            prior_direction = None
            if len(prior) >= internal_lookback:
                prior_high = max(c["high"] for c in prior[:-1])
                prior_low = min(c["low"] for c in prior[:-1])
                if prior[-1]["close"] > prior_high:
                    prior_direction = "LONG"
                elif prior[-1]["close"] < prior_low:
                    prior_direction = "SHORT"
            choch = prior_direction == ("SHORT" if side == "LONG" else "LONG")

            # Path 1: strong continuation, no exact retest required.
            if last == break_idx + 1:
                confirmation = candles[last]
                follows = (
                    confirmation["close"] > breaker["high"]
                    if side == "LONG"
                    else confirmation["close"] < breaker["low"]
                )
                if follows:
                    return {
                        "side": side, "path": "CONTINUATION", "idm": idm,
                        "idm_idx": sweep_idx, "break_level": level,
                        "break_idx": break_idx, "confirmation_idx": last,
                        "bos": True, "choch": choch, "mss": True,
                        "breakout_body_atr": body / break_atr,
                        "retest_exact": False,
                        "stop_extreme": min(sweep["low"], breaker["low"]) if side == "LONG" else max(sweep["high"], breaker["high"]),
                    }

            # Path 2: shallow structural pullback and reclaim, not FVG/OB.
            for retest_idx in range(break_idx + 1, min(last - 1, break_idx + retest_window) + 1):
                retest = candles[retest_idx]
                tau = _atr(candles, retest_idx) * sweep_buffer_atr
                touched = (
                    retest["low"] <= level + tau
                    if side == "LONG"
                    else retest["high"] >= level - tau
                )
                held = (
                    retest["close"] >= level - tau
                    if side == "LONG"
                    else retest["close"] <= level + tau
                )
                if not touched or not held or last != retest_idx + 1:
                    continue
                confirmation = candles[last]
                follows = (
                    confirmation["close"] > retest["high"]
                    if side == "LONG"
                    else confirmation["close"] < retest["low"]
                )
                if follows:
                    return {
                        "side": side, "path": "SHALLOW_RECLAIM", "idm": idm,
                        "idm_idx": sweep_idx, "break_level": level,
                        "break_idx": break_idx, "retest_idx": retest_idx,
                        "confirmation_idx": last, "bos": True, "choch": choch,
                        "mss": True, "breakout_body_atr": body / break_atr,
                        "retest_exact": False,
                        "stop_extreme": min(sweep["low"], retest["low"]) if side == "LONG" else max(sweep["high"], retest["high"]),
                    }
    return None
