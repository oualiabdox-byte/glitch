"""Unified SMC feature layer.

pyvsmc is optional and non-authoritative. The strategy never requires every
detected concept and never tunes thresholds against pyvsmc output.
"""

from __future__ import annotations

from typing import Any

try:
    import numpy as np
    import pyvsmc as _pyvsmc
except Exception:
    np = None
    _pyvsmc = None


def _last_true(value: Any) -> bool:
    if value is None:
        return False
    try:
        if np is not None:
            arr = np.asarray(value)
            return bool(arr.size and bool(arr.reshape(-1)[-1]))
        return bool(value[-1])
    except Exception:
        return bool(value)


def _last_number(value: Any):
    if value is None:
        return None
    try:
        if np is not None:
            arr = np.asarray(value)
            if not arr.size:
                return None
            return float(arr.reshape(-1)[-1])
        return float(value[-1])
    except Exception:
        return None


def analyze(candles: list[dict]) -> dict:
    """Return descriptive SMC facts from the supplied causal candle slice."""
    if len(candles) < 5 or _pyvsmc is None or np is None:
        return {"available": False, "engine": "local"}

    high = np.asarray([float(c["high"]) for c in candles], dtype=float)
    low = np.asarray([float(c["low"]) for c in candles], dtype=float)
    close = np.asarray([float(c["close"]) for c in candles], dtype=float)
    open_ = np.asarray([float(c["open"]) for c in candles], dtype=float)
    facts = {"available": True, "engine": "pyvsmc"}

    try:
        r = _pyvsmc.detect_fvg(high, low, close=close)
        facts["fvg_bullish"] = _last_true(getattr(r, "bullish", None))
        facts["fvg_bearish"] = _last_true(getattr(r, "bearish", None))
    except Exception:
        facts["fvg_bullish"] = facts["fvg_bearish"] = False

    try:
        r = _pyvsmc.detect_structure(
            high, low, close, window_size=2, break_mode="close"
        )
        facts["bos_bullish"] = _last_true(getattr(r, "bos_bullish", None))
        facts["bos_bearish"] = _last_true(getattr(r, "bos_bearish", None))
        facts["trend"] = _last_number(getattr(r, "trend", None))
    except Exception:
        facts["bos_bullish"] = facts["bos_bearish"] = False
        facts["trend"] = None

    try:
        r = _pyvsmc.detect_liquidity(high, low, close)
        facts["sweep_high"] = _last_true(getattr(r, "sweep_high", None))
        facts["sweep_low"] = _last_true(getattr(r, "sweep_low", None))
    except Exception:
        facts["sweep_high"] = facts["sweep_low"] = False

    try:
        r = _pyvsmc.detect_zones(high, low, close)
        facts["in_ote"] = _last_true(getattr(r, "in_ote", None))
        facts["premium"] = _last_true(getattr(r, "premium", None))
        facts["discount"] = _last_true(getattr(r, "discount", None))
    except Exception:
        facts["in_ote"] = facts["premium"] = facts["discount"] = False

    try:
        r = _pyvsmc.detect_order_blocks(
            open_, high, low, close, lookback=10, compute_mitigation=True
        )
        facts["bullish_ob"] = _last_true(getattr(r, "bullish_ob", None))
        facts["bearish_ob"] = _last_true(getattr(r, "bearish_ob", None))
        facts["ob_mitigated"] = _last_true(getattr(r, "mitigated", None))
        facts["ob_breaker"] = _last_true(getattr(r, "is_breaker", None))
    except Exception:
        facts["bullish_ob"] = facts["bearish_ob"] = False
        facts["ob_mitigated"] = facts["ob_breaker"] = False

    return facts
