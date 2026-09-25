from __future__ import annotations

from typing import Any

from .models import Candle, M5ExecutionConfirmation, Side, Swing


def find_swing_highs(candles: list[Candle], length: int = 3) -> list[Swing]:
    """Return confirmed pivots; a pivot at i is only knowable after i+length."""
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
    """Return confirmed pivots; a pivot at i is only knowable after i+length."""
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
    """Label confirmed swings for diagnostics only; labels do not set direction."""
    def label(items: list[Swing], kind: str) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        previous: Swing | None = None
        for swing in items:
            if previous is None:
                name = None
            elif kind == "HIGH":
                name = "HH" if swing.price > previous.price else "LH" if swing.price < previous.price else "EQH"
            else:
                name = "HL" if swing.price > previous.price else "LL" if swing.price < previous.price else "EQL"
            result.append({"index": swing.index, "price": swing.price, "time": swing.time, "label": name})
            previous = swing
        return result

    return label(highs, "HIGH"), label(lows, "LOW")


def _serialize_swings(swings: list[Swing], length: int, kind: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    previous: Swing | None = None
    for swing in swings:
        if previous is None:
            label = None
        elif kind == "HIGH":
            label = "HH" if swing.price > previous.price else "LH" if swing.price < previous.price else "EQH"
        else:
            label = "HL" if swing.price > previous.price else "LL" if swing.price < previous.price else "EQL"
        result.append({"index": swing.index, "confirmed_index": swing.index + length,
                       "price": swing.price, "time": swing.time, "label": label,
                       "kind": kind})
        previous = swing
    return result


def analyze_structure(candles: list[Candle], length: int = 3, tolerant: bool = True) -> dict[str, Any]:
    """Build the authoritative causal structure snapshot for one timeframe.

    Swings become eligible only at their right-confirmation candle. Every event
    is a body-close break of an eligible, unconsumed pivot. A first BOS gives a
    weak directional state; an opposite break is a CHOCH and leaves direction
    unclear until a same-side continuation BOS confirms the transition.
    ``tolerant`` remains accepted for API compatibility but no longer lets swing
    labels independently vote on direction.
    """
    del tolerant
    if length < 1:
        raise ValueError("length must be >= 1")
    highs = find_swing_highs(candles, length)
    lows = find_swing_lows(candles, length)
    high_by_confirmation = {s.index + length: s for s in highs}
    low_by_confirmation = {s.index + length: s for s in lows}
    confirmed_highs: list[Swing] = []
    confirmed_lows: list[Swing] = []
    broken_highs: set[int] = set()
    broken_lows: set[int] = set()
    events: list[dict[str, Any]] = []
    confirmed_side: Side | None = None
    pending_side: Side | None = None
    state = "UNDEFINED"

    for i, candle in enumerate(candles):
        # A swing is made available only at the close of its rightmost
        # confirmation candle; no earlier candle can break it in this replay.
        if i in high_by_confirmation:
            confirmed_highs.append(high_by_confirmation[i])
        if i in low_by_confirmation:
            confirmed_lows.append(low_by_confirmation[i])

        up_candidates = [s for s in confirmed_highs
                         if s.index not in broken_highs and candle.close > s.price]
        down_candidates = [s for s in confirmed_lows
                           if s.index not in broken_lows and candle.close < s.price]
        candidates: list[tuple[str, Swing]] = []
        if up_candidates:
            # If one close clears several old levels, consume all of them and
            # represent the move by its most recent structural level.
            broken_highs.update(s.index for s in up_candidates)
            candidates.append(("LONG", max(up_candidates, key=lambda s: s.index)))
        if down_candidates:
            broken_lows.update(s.index for s in down_candidates)
            candidates.append(("SHORT", max(down_candidates, key=lambda s: s.index)))
        if not candidates:
            continue

        # A valid OHLC close cannot be above a high and below a lower low at
        # once. If malformed/overlapping pivots nonetheless create ambiguity,
        # do not choose a direction or emit a potentially contradictory event.
        if len(candidates) != 1:
            state = "TRANSITION"
            confirmed_side = None
            pending_side = None
            continue

        side_text, pivot = candidates[0]
        side: Side = side_text  # type: ignore[assignment]
        if confirmed_side is None and pending_side is None:
            event_type = "BOS"
            state = "BULLISH_WEAK" if side == "LONG" else "BEARISH_WEAK"
            confirmed_side = side
        elif pending_side is not None:
            if side == pending_side:
                event_type = "BOS"
                confirmed_side = side
                pending_side = None
                state = "BULLISH" if side == "LONG" else "BEARISH"
            else:
                event_type = "CHOCH"
                pending_side = side
                state = "TRANSITION"
                confirmed_side = None
        elif side == confirmed_side:
            event_type = "BOS"
            state = "BULLISH" if side == "LONG" else "BEARISH"
        else:
            event_type = "CHOCH"
            pending_side = side
            confirmed_side = None
            state = "TRANSITION"

        events.append({
            "index": i, "time": candle.time, "type": event_type,
            "side": side, "level": pivot.price,
            "broken_swing_index": pivot.index,
            "broken_swing_time": pivot.time,
            "confirmed_swing_index": pivot.index + length,
        })

    labeled_highs = _serialize_swings(highs, length, "HIGH")
    labeled_lows = _serialize_swings(lows, length, "LOW")
    last_event = events[-1] if events else None
    side: Side | None = confirmed_side
    if last_event and last_event["type"] == "CHOCH":
        side = None
    protected: dict[str, Any] | None = None
    external_high: dict[str, Any] | None = None
    external_low: dict[str, Any] | None = None
    if side == "LONG" and last_event:
        eligible = [s for s in confirmed_lows if s.index not in broken_lows]
        if not eligible:
            eligible = [s for s in confirmed_lows if s.index < last_event["index"]]
        if eligible:
            pivot = eligible[-1]
            protected = {"kind": "LOW", "price": pivot.price, "index": pivot.index,
                         "time": pivot.time, "confirmed_index": pivot.index + length}
        # Keep the latest external objective even after it is consumed; the
        # strategy uses subsequent OHLC to report TARGET_ALREADY_REACHED rather
        # than silently substituting an older level or losing the reference.
        targets = list(confirmed_highs)
        if targets:
            pivot = max(targets, key=lambda s: s.index)
            external_high = {"price": pivot.price, "index": pivot.index,
                             "time": pivot.time, "confirmed_index": pivot.index + length}
        if protected:
            external_low = {"price": protected["price"], "index": protected["index"],
                            "time": protected["time"], "confirmed_index": protected["confirmed_index"]}
    elif side == "SHORT" and last_event:
        eligible = [s for s in confirmed_highs if s.index not in broken_highs]
        if not eligible:
            eligible = [s for s in confirmed_highs if s.index < last_event["index"]]
        if eligible:
            pivot = eligible[-1]
            protected = {"kind": "HIGH", "price": pivot.price, "index": pivot.index,
                         "time": pivot.time, "confirmed_index": pivot.index + length}
        targets = list(confirmed_lows)
        if targets:
            pivot = max(targets, key=lambda s: s.index)
            external_low = {"price": pivot.price, "index": pivot.index,
                            "time": pivot.time, "confirmed_index": pivot.index + length}
        if protected:
            external_high = {"price": protected["price"], "index": protected["index"],
                             "time": protected["time"], "confirmed_index": protected["confirmed_index"]}

    high_value = external_high["price"] if external_high else None
    low_value = external_low["price"] if external_low else None
    return {
        "state": state,
        "side": side,
        "protected_swing": protected,
        "external_high": high_value,
        "external_low": low_value,
        "external_high_index": external_high["index"] if external_high else None,
        "external_low_index": external_low["index"] if external_low else None,
        "external_high_swing": external_high,
        "external_low_swing": external_low,
        "highs": labeled_highs,
        "lows": labeled_lows,
        "events": events,
        "last_event": last_event,
        "equilibrium": ((high_value + low_value) / 2
                        if high_value is not None and low_value is not None else None),
        "swing_length": length,
        "closed_candle_count": len(candles),
    }


def detect_structure_events(candles: list[Candle], length: int = 3) -> list[dict[str, Any]]:
    """Compatibility API backed by the authoritative event stream."""
    return analyze_structure(candles, length)["events"]


def get_m5_execution_confirmation(candles: list[Candle], required_side: Side | None,
                                  swing_length: int = 3,
                                  structure: dict[str, Any] | None = None) -> M5ExecutionConfirmation:
    """Inspect the newest overall event, then freshness, then direction."""
    latest_closed_index = len(candles) - 1 if candles else None
    latest_closed_time = candles[-1].time if candles else None
    canonical = structure if structure is not None else analyze_structure(candles, swing_length)
    events = canonical["events"]
    latest = events[-1] if events else None
    if latest is None:
        reasons = ("M5_NO_STRUCTURE_EVENT",)
    elif latest["index"] != latest_closed_index:
        reasons = ("M5_EVENT_STALE",)
    elif required_side is not None and latest["side"] != required_side:
        reasons = ("M5_EVENT_DIRECTION_MISMATCH",)
    else:
        reasons = ()
    return M5ExecutionConfirmation(
        latest_closed_index=latest_closed_index,
        latest_closed_time=latest_closed_time,
        latest_event=latest,
        latest_event_index=latest["index"] if latest else None,
        latest_event_time=latest["time"] if latest else None,
        latest_event_side=latest["side"] if latest else None,
        latest_event_type=latest["type"] if latest else None,
        required_side=required_side,
        event_is_latest_close=bool(latest and latest["index"] == latest_closed_index),
        valid=not reasons,
        reason_codes=reasons,
    )


def find_relevant_liquidity_sweeps(candles: list[Candle], structure: dict[str, Any],
                                    side: Side, poi_bottom: float, poi_top: float,
                                    after_index: int, max_age_bars: int = 24) -> list[dict[str, Any]]:
    """Find recent close-confirmed pivot sweeps inside/through the active POI."""
    kind = "LOW" if side == "LONG" else "HIGH"
    swings = structure.get("lows" if kind == "LOW" else "highs", [])
    last_index = len(candles) - 1
    results: list[dict[str, Any]] = []
    for i in range(max(0, after_index + 1), len(candles)):
        candle = candles[i]
        if last_index - i > max_age_bars:
            continue
        # Require the sweep candle itself to intersect the H1 POI. This keeps
        # unrelated liquidity raids elsewhere in the lookback from qualifying.
        if candle.high < poi_bottom or candle.low > poi_top:
            continue
        for swing in swings:
            if swing["index"] >= i or swing["confirmed_index"] > i:
                continue
            level = float(swing["price"])
            swept = (candle.low < level and candle.close > level) if side == "LONG" else (
                candle.high > level and candle.close < level
            )
            if swept:
                results.append({"index": i, "time": candle.time, "side": side,
                                "type": "SELL_SIDE_SWEEP" if side == "LONG" else "BUY_SIDE_SWEEP",
                                "level": level, "swing_index": swing["index"],
                                "swing_time": swing["time"], "poi_overlap": True})
    return results
