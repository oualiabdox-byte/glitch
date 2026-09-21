"""Causal, stateful market-structure engine.

The engine works on closed candles only. Swings are confirmed only after
swing_length candles exist on both sides of the candidate.
"""

from __future__ import annotations


def find_swing_highs(candles, length=3):
    """Return confirmed swing highs. The last length candles cannot confirm."""
    if length < 1:
        raise ValueError("length must be >= 1")
    out = []
    for i in range(length, len(candles) - length):
        c = candles[i]
        left = [candles[i - j]["high"] for j in range(1, length + 1)]
        right = [candles[i + j]["high"] for j in range(1, length + 1)]
        if c["high"] >= max(left) and c["high"] > max(right):
            out.append({"time": c["time"], "high": c["high"], "idx": i})
    return out


def find_swing_lows(candles, length=3):
    """Return confirmed swing lows. The last length candles cannot confirm."""
    if length < 1:
        raise ValueError("length must be >= 1")
    out = []
    for i in range(length, len(candles) - length):
        c = candles[i]
        left = [candles[i - j]["low"] for j in range(1, length + 1)]
        right = [candles[i + j]["low"] for j in range(1, length + 1)]
        if c["low"] <= min(left) and c["low"] < min(right):
            out.append({"time": c["time"], "low": c["low"], "idx": i})
    return out


def _label_swings(highs, lows):
    labeled_highs = []
    for i, swing in enumerate(highs):
        item = dict(swing)
        item["label"] = "HH" if i == 0 or swing["high"] > highs[i - 1]["high"] else "LH"
        labeled_highs.append(item)

    labeled_lows = []
    for i, swing in enumerate(lows):
        item = dict(swing)
        item["label"] = "HL" if i == 0 or swing["low"] > lows[i - 1]["low"] else "LL"
        labeled_lows.append(item)
    return labeled_highs, labeled_lows


def _latest_before(items, idx):
    eligible = [x for x in items if x["idx"] < idx]
    return eligible[-1] if eligible else None


def detect_structure_events(candles, swing_length=3):
    """Detect causal BOS/CHOCH events from closes breaking confirmed swings."""
    highs = find_swing_highs(candles, swing_length)
    lows = find_swing_lows(candles, swing_length)
    labeled_highs, labeled_lows = _label_swings(highs, lows)

    events = []
    prior_state = None

    for i, candle in enumerate(candles):
        high = _latest_before(labeled_highs, i)
        low = _latest_before(labeled_lows, i)

        if high and candle["close"] > high["high"]:
            event_type = "CHOCH" if prior_state == "BEARISH" else "BOS"
            events.append({
                "time": candle["time"],
                "idx": i,
                "type": event_type,
                "direction": "BULLISH",
                "level": high["high"],
                "broken_swing_time": high["time"],
            })
            prior_state = "BULLISH"

        if low and candle["close"] < low["low"]:
            event_type = "CHOCH" if prior_state == "BULLISH" else "BOS"
            events.append({
                "time": candle["time"],
                "idx": i,
                "type": event_type,
                "direction": "BEARISH",
                "level": low["low"],
                "broken_swing_time": low["time"],
            })
            prior_state = "BEARISH"

    return events


def analyze_structure(candles, swing_length=3):
    """Return the complete structural state for the supplied closed history."""
    if swing_length < 1:
        raise ValueError("swing_length must be >= 1")
    if len(candles) < swing_length * 2 + 3:
        return {
            "bias": None,
            "structure": "UNDEFINED",
            "highs": [],
            "lows": [],
            "last_event": None,
            "external_high": None,
            "external_low": None,
        }

    highs = find_swing_highs(candles, swing_length)
    lows = find_swing_lows(candles, swing_length)
    labeled_highs, labeled_lows = _label_swings(highs, lows)

    high_label = labeled_highs[-1]["label"] if labeled_highs else None
    low_label = labeled_lows[-1]["label"] if labeled_lows else None

    if high_label == "HH" and low_label == "HL":
        bias = "LONG"
        structure = "BULLISH"
    elif high_label == "LH" and low_label == "LL":
        bias = "SHORT"
        structure = "BEARISH"
    else:
        bias = None
        structure = "MIXED"

    events = detect_structure_events(candles, swing_length=swing_length)
    last_event = events[-1] if events else None

    return {
        "bias": bias,
        "structure": structure,
        "highs": labeled_highs,
        "lows": labeled_lows,
        "last_event": last_event,
        "external_high": labeled_highs[-1]["high"] if labeled_highs else None,
        "external_low": labeled_lows[-1]["low"] if labeled_lows else None,
    }


def build_htf_context(candles_4h, swing_length=3):
    """Build the 4H HTF context used by the strategy."""
    result = analyze_structure(candles_4h, swing_length=swing_length)
    if result["external_high"] is not None and result["external_low"] is not None:
        high = result["external_high"]
        low = result["external_low"]
        result["equilibrium"] = (high + low) / 2.0
        close = candles_4h[-1]["close"]
        if close < result["equilibrium"]:
            result["premium_discount"] = "DISCOUNT"
        elif close > result["equilibrium"]:
            result["premium_discount"] = "PREMIUM"
        else:
            result["premium_discount"] = "EQUILIBRIUM"
    else:
        result["equilibrium"] = None
        result["premium_discount"] = None
    result["timeframe"] = "4H"
    return result


def is_higher_timeframe_uptrend(candles_4h):
    """Compatibility wrapper around the real structure engine."""
    context = build_htf_context(candles_4h)
    if context["structure"] == "BULLISH":
        return "uptrend"
    if context["structure"] == "BEARISH":
        return "downtrend"
    return None


def mss_confirmed(candles_1h, direction, reference_time, swing_length=3):
    """Confirm a post-reference structural shift using closed candles only."""
    pre = [c for c in candles_1h if c["time"] <= reference_time]
    post = [c for c in candles_1h if c["time"] > reference_time]
    if not pre or not post:
        return False, None

    if direction == "LONG":
        swings = find_swing_highs(pre, length=swing_length)
        if not swings:
            return False, None
        ref = swings[-1]["high"]
        for candle in post:
            if candle["close"] > ref:
                return True, ref
    elif direction == "SHORT":
        swings = find_swing_lows(pre, length=swing_length)
        if not swings:
            return False, None
        ref = swings[-1]["low"]
        for candle in post:
            if candle["close"] < ref:
                return True, ref

    return False, None
