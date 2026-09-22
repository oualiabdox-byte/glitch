"""Causal H1 breakout-and-retest entry model.

A level is created only from a confirmed swing. A breakout requires a closed
body beyond the level, followed by a later retest and a later confirmation
close. The caller must execute no earlier than the next bar.
"""
from __future__ import annotations

from . import market_structure


def _atr(candles, end_idx, period=14):
    if end_idx < 2:
        return 0.0
    start = max(1, end_idx - period)
    ranges = []
    for i in range(start, end_idx):
        h, low = candles[i]["high"], candles[i]["low"]
        previous_close = candles[i - 1]["close"]
        ranges.append(max(h - low, abs(h - previous_close), abs(low - previous_close)))
    return sum(ranges) / len(ranges) if ranges else 0.0


def _level_before(candles, end_idx, side, swing_length):
    if end_idx < swing_length * 2 + 1:
        return None
    confirmed = candles[:end_idx]
    swings = (
        market_structure.find_swing_highs(confirmed, swing_length)
        if side == "LONG"
        else market_structure.find_swing_lows(confirmed, swing_length)
    )
    if not swings:
        return None
    swing = swings[-1]
    return {
        "price": swing["high"] if side == "LONG" else swing["low"],
        "time": swing["time"],
        "idx": swing["idx"],
    }


def find_breakout_retest(
    candles,
    side,
    end_idx=None,
    swing_length=3,
    breakout_body_atr=0.50,
    retest_window=6,
    zone_atr=0.05,
):
    """Return a closed-bar breakout/retest confirmation ending at ``end_idx``.

    The returned signal is known only after the confirmation bar closes. It is
    therefore safe for a caller to submit at the following bar's executable
    open. No current-bar high/low is used before that bar closes.
    """
    if side not in {"LONG", "SHORT"}:
        raise ValueError("side must be LONG or SHORT")
    if swing_length < 2 or retest_window < 1 or breakout_body_atr < 0 or zone_atr < 0:
        raise ValueError("invalid breakout/retest parameters")
    last = len(candles) - 1 if end_idx is None else int(end_idx)
    if last >= len(candles):
        raise IndexError("end_idx is outside candle data")
    if last < swing_length * 2 + 3:
        return None

    first_breakout = max(swing_length * 2 + 1, last - retest_window - 12)
    for breakout_idx in range(last - 2, first_breakout - 1, -1):
        level = _level_before(candles, breakout_idx, side, swing_length)
        if not level:
            continue
        atr = _atr(candles, breakout_idx)
        if atr <= 0:
            continue
        buffer = atr * zone_atr
        breakout = candles[breakout_idx]
        body = abs(breakout["close"] - breakout["open"])
        if body < atr * breakout_body_atr:
            continue
        if side == "LONG" and breakout["close"] <= level["price"] + buffer:
            continue
        if side == "SHORT" and breakout["close"] >= level["price"] - buffer:
            continue

        retest_limit = min(last - 1, breakout_idx + retest_window)
        for retest_idx in range(breakout_idx + 1, retest_limit + 1):
            retest = candles[retest_idx]
            touched = (
                retest["low"] <= level["price"] + buffer
                if side == "LONG"
                else retest["high"] >= level["price"] - buffer
            )
            held = (
                retest["close"] >= level["price"] - buffer
                if side == "LONG"
                else retest["close"] <= level["price"] + buffer
            )
            if not touched or not held:
                continue
            confirmation_idx = retest_idx + 1
            if confirmation_idx != last:
                continue
            confirmation = candles[confirmation_idx]
            follow_through = (
                confirmation["close"] > retest["high"]
                if side == "LONG"
                else confirmation["close"] < retest["low"]
            )
            if not follow_through:
                continue
            return {
                "side": side,
                "level": level["price"],
                "level_time": level["time"],
                "breakout_idx": breakout_idx,
                "breakout_time": breakout["time"],
                "retest_idx": retest_idx,
                "retest_time": retest["time"],
                "confirmation_idx": confirmation_idx,
                "confirmation_time": confirmation["time"],
                "zone_buffer": buffer,
                "breakout_body_atr": body / atr,
                "stop_extreme": min(retest["low"], breakout["low"]) if side == "LONG" else max(retest["high"], breakout["high"]),
            }
    return None
