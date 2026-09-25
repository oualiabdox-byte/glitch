from __future__ import annotations

from typing import Any

from .models import Candle, M5ExecutionConfirmation, Side, Swing


def find_swing_highs(candles: list[Candle], length: int = 3) -> list[Swing]:
    if length < 1:
        raise ValueError("length must be >= 1")
    out: list[Swing] = []
    for i in range(length, len(candles) - length):
        value = candles[i].high
        left = [candles[i - j].high for j in range(1, length + 1)]
        right = [candles[i + j].high for j in range(1, length + 1)]
        if value >= max(left) and value > max(right):
            out.append(Swing(i, "HIGH", value, candles[i].time))
    return out


def find_swing_lows(candles: list[Candle], length: int = 3) -> list[Swing]:
    if length < 1:
        raise ValueError("length must be >= 1")
    out: list[Swing] = []
    for i in range(length, len(candles) - length):
        value = candles[i].low
        left = [candles[i - j].low for j in range(1, length + 1)]
        right = [candles[i + j].low for j in range(1, length + 1)]
        if value <= min(left) and value < min(right):
            out.append(Swing(i, "LOW", value, candles[i].time))
    return out


def label_swings(highs: list[Swing], lows: list[Swing]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    labeled_highs: list[dict[str, Any]] = []
    previous = None
    for swing in highs:
        label = None if previous is None else "HH" if swing.price > previous.price else "LH"
        labeled_highs.append({"index": swing.index, "price": swing.price, "time": swing.time, "label": label})
        previous = swing
    labeled_lows: list[dict[str, Any]] = []
    previous = None
    for swing in lows:
        label = None if previous is None else "HL" if swing.price > previous.price else "LL"
        labeled_lows.append({"index": swing.index, "price": swing.price, "time": swing.time, "label": label})
        previous = swing
    return labeled_highs, labeled_lows


def detect_structure_events(candles: list[Candle], length: int = 3) -> list[dict[str, Any]]:
    """Emit body-close BOS/CHOCH events once per confirmed swing level."""
    highs = find_swing_highs(candles, length)
    lows = find_swing_lows(candles, length)
    labeled_highs, labeled_lows = label_swings(highs, lows)
    events: list[dict[str, Any]] = []
    state: str | None = None
    broken_highs: set[int] = set()
    broken_lows: set[int] = set()
    for i, candle in enumerate(candles):
        high = next((item for item in reversed(labeled_highs) if item["index"] < i), None)
        low = next((item for item in reversed(labeled_lows) if item["index"] < i), None)
        if high and high["index"] not in broken_highs and candle.close > high["price"]:
            event_type = "CHOCH" if state == "BEARISH" else "BOS"
            events.append({"index": i, "time": candle.time, "type": event_type,
                           "side": "LONG", "level": high["price"],
                           "broken_swing_index": high["index"], "broken_swing_time": high["time"]})
            broken_highs.add(high["index"])
            state = "BULLISH"
        if low and low["index"] not in broken_lows and candle.close < low["price"]:
            event_type = "CHOCH" if state == "BULLISH" else "BOS"
            events.append({"index": i, "time": candle.time, "type": event_type,
                           "side": "SHORT", "level": low["price"],
                           "broken_swing_index": low["index"], "broken_swing_time": low["time"]})
            broken_lows.add(low["index"])
            state = "BEARISH"
    return events


def get_m5_execution_confirmation(candles: list[Candle], required_side: Side | None,
                                  swing_length: int = 3) -> M5ExecutionConfirmation:
    """Evaluate the newest overall M5 event against the latest closed candle.

    This is the sole freshness/direction decision used by both SVL diagnostics
    and the execution engine. Direction is intentionally checked only after
    selecting the newest event, so a newer opposite-direction event cannot be
    hidden by an older event in the required direction.
    """
    latest_closed_index = len(candles) - 1 if candles else None
    latest_closed_time = candles[-1].time if candles else None
    events = detect_structure_events(candles, swing_length) if candles else []
    latest = events[-1] if events else None
    if latest is None:
        reasons = ("M5_NO_STRUCTURE_EVENT",)
    elif latest["index"] != latest_closed_index:
        reasons = ("M5_EVENT_STALE",)
    elif required_side is not None and latest["side"] != required_side:
        reasons = ("M5_EVENT_DIRECTION_MISMATCH",)
    else:
        reasons = ()
    event_is_latest_close = bool(latest and latest["index"] == latest_closed_index)
    return M5ExecutionConfirmation(
        latest_closed_index=latest_closed_index,
        latest_closed_time=latest_closed_time,
        latest_event=latest,
        latest_event_index=latest["index"] if latest else None,
        latest_event_time=latest["time"] if latest else None,
        latest_event_side=latest["side"] if latest else None,
        latest_event_type=latest["type"] if latest else None,
        required_side=required_side,
        event_is_latest_close=event_is_latest_close,
        valid=not reasons,
        reason_codes=reasons,
    )


def analyze_structure(candles: list[Candle], length: int = 3, tolerant: bool = True) -> dict[str, Any]:
    highs = find_swing_highs(candles, length)
    lows = find_swing_lows(candles, length)
    labeled_highs, labeled_lows = label_swings(highs, lows)
    high_label = labeled_highs[-1]["label"] if labeled_highs else None
    low_label = labeled_lows[-1]["label"] if labeled_lows else None
    side: Side | None = None
    state = "UNDEFINED"
    if high_label == "HH" and low_label == "HL":
        side, state = "LONG", "BULLISH"
    elif high_label == "LH" and low_label == "LL":
        side, state = "SHORT", "BEARISH"
    elif tolerant and labeled_highs and labeled_lows:
        recent_highs = [item["label"] for item in labeled_highs[-3:] if item["label"]]
        recent_lows = [item["label"] for item in labeled_lows[-3:] if item["label"]]
        bullish_score = recent_highs.count("HH") + recent_lows.count("HL")
        bearish_score = recent_highs.count("LH") + recent_lows.count("LL")
        if bullish_score >= 2 and bullish_score > bearish_score:
            side, state = "LONG", "BULLISH_WEAK"
        elif bearish_score >= 2 and bearish_score > bullish_score:
            side, state = "SHORT", "BEARISH_WEAK"
        else:
            state = "MIXED"
    elif labeled_highs and labeled_lows:
        state = "MIXED"
    events = detect_structure_events(candles, length)
    external_high = labeled_highs[-1]["price"] if labeled_highs else None
    external_low = labeled_lows[-1]["price"] if labeled_lows else None
    return {"side": side, "state": state, "highs": labeled_highs, "lows": labeled_lows,
            "events": events, "last_event": events[-1] if events else None,
            "external_high": external_high, "external_low": external_low,
            "external_high_index": (labeled_highs[-1]["index"] if labeled_highs else None),
            "external_low_index": (labeled_lows[-1]["index"] if labeled_lows else None),
            "equilibrium": ((external_high + external_low) / 2 if external_high is not None and external_low is not None else None)}
