"""Causal market-structure engine for SMC/ICT research.

Only closed candles are used. A swing becomes available only after
swing_length candles have closed on its right side.
"""

from __future__ import annotations


def find_swing_highs(candles, length=3):
    if length < 1:
        raise ValueError("length must be >= 1")
    out = []
    for i in range(length, len(candles) - length):
        value = candles[i]["high"]
        left = [candles[i - j]["high"] for j in range(1, length + 1)]
        right = [candles[i + j]["high"] for j in range(1, length + 1)]
        if value >= max(left) and value > max(right):
            out.append({"time": candles[i]["time"], "high": value, "idx": i})
    return out


def find_swing_lows(candles, length=3):
    if length < 1:
        raise ValueError("length must be >= 1")
    out = []
    for i in range(length, len(candles) - length):
        value = candles[i]["low"]
        left = [candles[i - j]["low"] for j in range(1, length + 1)]
        right = [candles[i + j]["low"] for j in range(1, length + 1)]
        if value <= min(left) and value < min(right):
            out.append({"time": candles[i]["time"], "low": value, "idx": i})
    return out


def _label_swings(highs, lows):
    labeled_highs = []
    previous = None
    for swing in highs:
        item = dict(swing)
        item["label"] = (
            None if previous is None
            else "HH" if swing["high"] > previous["high"] else "LH"
        )
        labeled_highs.append(item)
        previous = swing

    labeled_lows = []
    previous = None
    for swing in lows:
        item = dict(swing)
        item["label"] = (
            None if previous is None
            else "HL" if swing["low"] > previous["low"] else "LL"
        )
        labeled_lows.append(item)
        previous = swing
    return labeled_highs, labeled_lows


def _latest_before(items, idx):
    for item in reversed(items):
        if item["idx"] < idx:
            return item
    return None


def _last_two_confirmed(items):
    return items[-2:] if len(items) >= 2 else []


def _structure_state(highs, lows):
    hs = _last_two_confirmed(highs)
    ls = _last_two_confirmed(lows)
    if len(hs) < 2 or len(ls) < 2:
        return None, "UNDEFINED"
    high_label = hs[-1]["label"]
    low_label = ls[-1]["label"]
    if high_label == "HH" and low_label == "HL":
        return "LONG", "BULLISH"
    if high_label == "LH" and low_label == "LL":
        return "SHORT", "BEARISH"
    return None, "MIXED"


def detect_structure_events(candles, swing_length=3):
    """Emit each structural break once; broken levels are consumed."""
    highs = find_swing_highs(candles, swing_length)
    lows = find_swing_lows(candles, swing_length)
    labeled_highs, labeled_lows = _label_swings(highs, lows)

    events = []
    state = None
    broken_high_idx = set()
    broken_low_idx = set()

    for i, candle in enumerate(candles):
        high = _latest_before(labeled_highs, i)
        low = _latest_before(labeled_lows, i)

        if high and high["idx"] not in broken_high_idx and candle["close"] > high["high"]:
            event_type = "CHOCH" if state == "BEARISH" else "BOS"
            events.append({
                "time": candle["time"], "idx": i, "type": event_type,
                "direction": "BULLISH", "level": high["high"],
                "broken_swing_time": high["time"],
            })
            broken_high_idx.add(high["idx"])
            state = "BULLISH"

        if low and low["idx"] not in broken_low_idx and candle["close"] < low["low"]:
            event_type = "CHOCH" if state == "BULLISH" else "BOS"
            events.append({
                "time": candle["time"], "idx": i, "type": event_type,
                "direction": "BEARISH", "level": low["low"],
                "broken_swing_time": low["time"],
            })
            broken_low_idx.add(low["idx"])
            state = "BEARISH"

    return events


def analyze_structure(candles, swing_length=3):
    if swing_length < 1:
        raise ValueError("swing_length must be >= 1")
    if len(candles) < swing_length * 2 + 3:
        return {
            "bias": None, "structure": "UNDEFINED", "highs": [], "lows": [],
            "last_event": None, "external_high": None, "external_low": None,
            "dealing_range": None,
        }

    highs = find_swing_highs(candles, swing_length)
    lows = find_swing_lows(candles, swing_length)
    labeled_highs, labeled_lows = _label_swings(highs, lows)
    bias, structure = _structure_state(labeled_highs, labeled_lows)
    events = detect_structure_events(candles, swing_length)

    external_high = labeled_highs[-1]["high"] if labeled_highs else None
    external_low = labeled_lows[-1]["low"] if labeled_lows else None
    dealing_range = (
        {"high": external_high, "low": external_low,
         "equilibrium": (external_high + external_low) / 2.0}
        if external_high is not None and external_low is not None else None
    )

    return {
        "bias": bias, "structure": structure,
        "highs": labeled_highs, "lows": labeled_lows,
        "last_event": events[-1] if events else None,
        "external_high": external_high, "external_low": external_low,
        "dealing_range": dealing_range,
    }


def build_htf_context(candles_4h, swing_length=3):
    result = analyze_structure(candles_4h, swing_length=swing_length)
    if result["dealing_range"] is None or not candles_4h:
        result["equilibrium"] = None
        result["premium_discount"] = None
        result["timeframe"] = "4H"
        return result

    eq = result["dealing_range"]["equilibrium"]
    close = candles_4h[-1]["close"]
    result["equilibrium"] = eq
    result["premium_discount"] = (
        "DISCOUNT" if close < eq else "PREMIUM" if close > eq else "EQUILIBRIUM"
    )
    result["timeframe"] = "4H"
    return result


def is_higher_timeframe_uptrend(candles_4h):
    context = build_htf_context(candles_4h)
    if context["structure"] == "BULLISH":
        return "uptrend"
    if context["structure"] == "BEARISH":
        return "downtrend"
    return None


def mss_confirmed(candles_1h, direction, reference_time, swing_length=3):
    pre = [c for c in candles_1h if c["time"] <= reference_time]
    post = [c for c in candles_1h if c["time"] > reference_time]
    if not pre or not post:
        return False, None

    if direction == "LONG":
        swings = find_swing_highs(pre, swing_length)
        if not swings:
            return False, None
        level = swings[-1]["high"]
        for candle in post:
            if candle["close"] > level:
                return True, level
    elif direction == "SHORT":
        swings = find_swing_lows(pre, swing_length)
        if not swings:
            return False, None
        level = swings[-1]["low"]
        for candle in post:
            if candle["close"] < level:
                return True, level
    return False, None
