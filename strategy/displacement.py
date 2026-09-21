"""Causal displacement detection without indicator stacking."""
from __future__ import annotations

from statistics import pstdev


def _atr(candles, end_idx, period=14):
    start = max(1, end_idx - period)
    if start >= end_idx:
        return 0.0
    trs = []
    for i in range(start, end_idx):
        h, l = candles[i]["high"], candles[i]["low"]
        pc = candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else 0.0


def is_displaced(
    candles_1h,
    candle_idx,
    min_body_atr_ratio=1.0,
    mode="body_atr",
    std_multiple=2.5,
):
    """Check a closed candle using only candles before it."""
    if candle_idx < 1:
        return False
    prev = candles_1h[max(0, candle_idx - 20):candle_idx]
    if not prev:
        return False

    cur = candles_1h[candle_idx]
    body = abs(cur["close"] - cur["open"])

    if mode == "average_body":
        avg_body = sum(abs(c["close"] - c["open"]) for c in prev) / len(prev)
        return avg_body > 0 and body >= avg_body * min_body_atr_ratio

    if mode == "body_std":
        bodies = [abs(c["close"] - c["open"]) for c in prev]
        std = pstdev(bodies) if len(bodies) > 1 else 0.0
        return std > 0 and body >= std * std_multiple

    atr = _atr(candles_1h, candle_idx)
    if atr <= 0:
        return False

    if mode == "range_atr":
        prev_close = candles_1h[candle_idx - 1]["close"]
        true_range = max(
            cur["high"] - cur["low"],
            abs(cur["high"] - prev_close),
            abs(cur["low"] - prev_close),
        )
        return true_range / atr >= min_body_atr_ratio

    return body / atr >= min_body_atr_ratio
