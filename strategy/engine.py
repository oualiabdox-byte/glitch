from __future__ import annotations

from statistics import median
from typing import Any

from .models import BosEvent, Candle, Decision, FairValueGap, M5ExecutionConfirmation, Side, Swing
from .structure import analyze_structure, get_m5_execution_confirmation, find_swing_highs, find_swing_lows
from .svl import alignment_for_execution


class Strategy:
    """Deterministic 1H location / M5 execution model.

    The engine never submits orders. It returns a signal or an auditable reason
    for rejection. All decisions use closed candles supplied by the caller.
    """

    def __init__(self, swing_left: int = 3, swing_right: int = 3, min_rr: float = 0.0,
                 stop_buffer: float = 0.0, svl_require_alignment: bool = False,
                 svl_profile_bins: int = 24, svl_equal_tolerance_pct: float = 0.001):
        if swing_left != swing_right:
            raise ValueError("swing_left and swing_right must match for causal structure")
        self.swing_left = swing_left
        self.swing_right = swing_right
        self.min_rr = min_rr
        self.stop_buffer = max(0.0, stop_buffer)
        self.svl_require_alignment = bool(svl_require_alignment)
        self.svl_profile_bins = max(4, int(svl_profile_bins))
        self.svl_equal_tolerance_pct = max(0.0, float(svl_equal_tolerance_pct))

    def evaluate(self, h1_rows: list[dict[str, Any]], m5_rows: list[dict[str, Any]]) -> Decision:
        h1 = [Candle.from_dict(row) for row in h1_rows]
        m5 = [Candle.from_dict(row) for row in m5_rows]
        evidence: dict[str, Any] = {"timeframes": {"context": "1H", "execution": "M5"}}
        if len(h1) < 20 or len(m5) < 20:
            return Decision("NO_TRADE", ["INSUFFICIENT_HISTORY"], evidence=evidence)

        evidence["svl"] = alignment_for_execution(
            h1_rows, m5_rows, self.swing_left, self.svl_profile_bins,
            self.svl_equal_tolerance_pct,
        )

        h_structure = analyze_structure(h1, self.swing_left)
        structure = {
            "side": h_structure["side"], "state": h_structure["state"],
            "protected_swing": (h_structure["external_low"] if h_structure["side"] == "LONG"
                                 else h_structure["external_high"]),
            "last_event": h_structure["last_event"],
        }
        evidence["h1_structure"] = structure
        if structure["side"] is None:
            return Decision("NO_TRADE", ["H1_STRUCTURE_UNCLEAR"], evidence=evidence)
        side: Side = structure["side"]
        if self.svl_require_alignment and not evidence["svl"]["aligned_for_trade"]:
            return Decision("NO_TRADE", ["SVL_NOT_ALIGNED"], side=side, evidence=evidence)

        dealing = (h_structure["external_low"], h_structure["external_high"])
        if dealing[0] is None or dealing[1] is None or dealing[1] <= dealing[0]:
            dealing = None
        if dealing is None:
            return Decision("NO_TRADE", ["H1_DEALING_RANGE_UNAVAILABLE"], side=side, evidence=evidence)
        low, high = dealing
        equilibrium = (low + high) / 2
        evidence["h1_dealing_range"] = {"low": low, "high": high, "equilibrium": equilibrium,
                                         "location": "DISCOUNT" if side == "LONG" else "PREMIUM"}

        fvg = find_location_fvg(h1, side, low, high)
        if fvg is None:
            return Decision("NO_TRADE", ["H1_POI_NOT_FOUND_IN_LOCATION"], side=side, evidence=evidence)
        evidence["h1_poi"] = {"index": fvg.index, "bottom": fvg.bottom, "top": fvg.top, "time": fvg.time}

        current = m5[-1]
        if not fvg.overlaps(current):
            return Decision("NO_TRADE", ["PRICE_NOT_AT_H1_POI"], side=side, evidence=evidence)

        m_structure = analyze_structure(m5, self.swing_left)
        m_swings = [Swing(item["index"], "HIGH", item["price"], item["time"])
                    for item in m_structure["highs"]]
        m_swings += [Swing(item["index"], "LOW", item["price"], item["time"])
                     for item in m_structure["lows"]]
        bos = find_latest_bos(m5, m_swings, side, self.swing_left)
        if bos is None:
            execution_codes = evidence["svl"].get("execution", {}).get("reason_codes", [])
            m5_reason = next((code for code in execution_codes if code.startswith("M5_")),
                             "M5_NO_STRUCTURE_EVENT")
            return Decision("NO_TRADE", [m5_reason], side=side, evidence=evidence)
        evidence["m5_bos"] = {"index": bos.index, "level": bos.level, "close": bos.close,
                               "strength": bos.strength, "body_ratio": bos.body_ratio,
                               "type": getattr(bos, "event_type", "BOS"), "time": bos.time}

        stop_swing = latest_opposite_swing(m_swings, bos.index, side)
        if stop_swing is None:
            return Decision("NO_TRADE", ["M5_STRUCTURAL_STOP_UNAVAILABLE"], side=side, evidence=evidence)
        entry = current.close
        # A minor M5 swing can sit inside the larger liquidity pool. For a
        # long, protect below both the relevant M5 low and the H1 protected
        # low; mirror this above both highs for a short.
        h1_protected = h_structure["external_low"] if side == "LONG" else h_structure["external_high"]
        if side == "LONG":
            stop_anchor = min(stop_swing.price, h1_protected)
            stop = stop_anchor - self.stop_buffer
            target = high
            target_index = h_structure["external_high_index"]
            target_reached_before_entry = target_index is not None and target_index < len(h1) - 1 and high >= max(c.high for c in h1[target_index + 1:])
        else:
            stop_anchor = max(stop_swing.price, h1_protected)
            stop = stop_anchor + self.stop_buffer
            target = low
            target_index = h_structure["external_low_index"]
            target_reached_before_entry = target_index is not None and target_index < len(h1) - 1 and low <= min(c.low for c in h1[target_index + 1:])
        risk = abs(entry - stop)
        reward = (target - entry) if side == "LONG" else (entry - target)
        if risk <= 0 or reward <= 0:
            return Decision("NO_TRADE", ["INVALID_RISK_GEOMETRY"], side=side, evidence=evidence)
        rr = reward / risk
        evidence["m5_stop_swing"] = {"kind": stop_swing.kind, "price": stop_swing.price, "time": stop_swing.time}
        evidence["protected_stop_anchor"] = {"h1_price": h1_protected, "selected_price": stop_anchor,
                                               "buffer": self.stop_buffer}
        evidence["h1_target"] = {"price": target, "index": target_index,
                                  "already_reached_before_entry": target_reached_before_entry}
        if target_reached_before_entry:
            return Decision("NO_TRADE", ["H1_TARGET_ALREADY_REACHED"], side=side, evidence=evidence)
        if rr < self.min_rr:
            return Decision("NO_TRADE", ["RISK_REWARD_BELOW_MINIMUM"], side=side, risk_reward=rr, evidence=evidence)
        return Decision("SIGNAL", [], side=side, entry_price=entry, stop_price=stop,
                        target_price=target, risk_reward=rr, evidence=evidence)


def find_swings(candles: list[Candle], left: int = 2, right: int = 2) -> list[Swing]:
    result: list[Swing] = []
    for i in range(left, len(candles) - right):
        c = candles[i]
        before = candles[i-left:i]
        after = candles[i+1:i+right+1]
        if c.high > max(x.high for x in before + after):
            result.append(Swing(i, "HIGH", c.high, c.time))
        if c.low < min(x.low for x in before + after):
            result.append(Swing(i, "LOW", c.low, c.time))
    return result


def infer_structure(swings: list[Swing]) -> dict[str, Any]:
    highs = [s for s in swings if s.kind == "HIGH"]
    lows = [s for s in swings if s.kind == "LOW"]
    if len(highs) < 2 or len(lows) < 2:
        return {"side": None, "state": "UNKNOWN"}
    hh = highs[-1].price > highs[-2].price
    hl = lows[-1].price > lows[-2].price
    lh = highs[-1].price < highs[-2].price
    ll = lows[-1].price < lows[-2].price
    if hh and hl:
        return {"side": "LONG", "state": "BULLISH", "protected_swing": lows[-1].price,
                "last_high": highs[-1].price, "last_low": lows[-1].price}
    if lh and ll:
        return {"side": "SHORT", "state": "BEARISH", "protected_swing": highs[-1].price,
                "last_high": highs[-1].price, "last_low": lows[-1].price}
    return {"side": None, "state": "TRANSITION_OR_RANGE"}


def dealing_range(swings: list[Swing], side: Side) -> tuple[float, float] | None:
    highs = [s.price for s in swings if s.kind == "HIGH"]
    lows = [s.price for s in swings if s.kind == "LOW"]
    if not highs or not lows:
        return None
    low, high = lows[-1], highs[-1]
    if high <= low:
        return None
    return low, high


def find_location_fvg(candles: list[Candle], side: Side, low: float, high: float) -> FairValueGap | None:
    midpoint = (low + high) / 2
    candidates: list[FairValueGap] = []
    for i in range(2, len(candles)):
        one, three = candles[i - 2], candles[i]
        if side == "LONG" and three.low > one.high:
            bottom, top = one.high, three.low
            # The gap only needs to reach the discount half. This allows a
            # narrow gap straddling equilibrium while rejecting premium-only
            # gaps for longs.
            if bottom <= midpoint:
                candidates.append(FairValueGap(i, side, bottom, top, three.time))
        if side == "SHORT" and three.high < one.low:
            bottom, top = three.high, one.low
            # Mirror the long rule: the gap must reach the premium half.
            if top >= midpoint:
                candidates.append(FairValueGap(i, side, bottom, top, three.time))
    return candidates[-1] if candidates else None


def find_latest_bos(candles: list[Candle], swings: list[Swing], side: Side,
                    swing_length: int = 3,
                    confirmation: M5ExecutionConfirmation | None = None) -> BosEvent | None:
    confirmation = confirmation or get_m5_execution_confirmation(candles, side, swing_length)
    if not confirmation.valid or confirmation.latest_event is None:
        return None
    event = confirmation.latest_event
    i = event["index"]
    c = candles[i]
    bodies = [abs(x.close - x.open) for x in candles[max(0, i-10):i] if x.close != x.open]
    median_body = median(bodies) if bodies else abs(c.close - c.open)
    ratio = abs(c.close - c.open) / median_body if median_body else 0.0
    strength = "STRONG" if ratio >= 1.5 else "NORMAL" if ratio >= 0.75 else "WEAK"
    return BosEvent(i, side, event["level"], c.close, strength, ratio, c.time, event["type"])


def latest_opposite_swing(swings: list[Swing], before_index: int, side: Side) -> Swing | None:
    kind = "LOW" if side == "LONG" else "HIGH"
    options = [s for s in swings if s.kind == kind and s.index < before_index]
    return options[-1] if options else None
