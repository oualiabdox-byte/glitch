from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median
from typing import Any

from .models import BosEvent, Candle, Decision, FairValueGap, M5ExecutionConfirmation, PointOfInterest, Side, Swing
from .structure import (analyze_structure, find_relevant_liquidity_sweeps,
                        get_m5_execution_confirmation)
from .htf_context import build_higher_timeframe_context
from .poi_confluence import build_poi_confluence
from .svl import alignment_for_execution
from .timing import as_utc, in_kill_zone, session_context


class Strategy:
    """Deterministic closed-bar H1 location / M5 execution model.

    This class emits only a signal or an auditable rejection. It never submits
    orders. All directional decisions derive from the canonical structure event
    stream in ``strategy.structure``.
    """

    def __init__(self, swing_left: int = 3, swing_right: int = 3, min_rr: float = 0.0,
                 stop_buffer: float = 0.0, svl_require_alignment: bool = False,
                 svl_profile_bins: int = 24, svl_equal_tolerance_pct: float = 0.001,
                 allow_weak_structure: bool = True,
                 allow_equilibrium_overlapping_fvg: bool = True,
                 setup_max_age_hours: int = 72,
                 m5_confirmation_mode: str = "CHOCH_OR_BOS",
                 require_killzone: bool = False,
                 require_displacement: bool = False,
                 min_displacement_ratio: float = 1.0,
                 require_poi_confluence: bool = False):
        if swing_left != swing_right:
            raise ValueError("swing_left and swing_right must match for causal structure")
        if swing_left < 1:
            raise ValueError("swing_length must be >= 1")
        if min_rr < 0:
            raise ValueError("min_rr must be >= 0")
        self.swing_left = swing_left
        self.swing_right = swing_right
        self.min_rr = float(min_rr)
        self.stop_buffer = max(0.0, float(stop_buffer))
        self.svl_require_alignment = bool(svl_require_alignment)
        self.svl_profile_bins = max(4, int(svl_profile_bins))
        self.svl_equal_tolerance_pct = max(0.0, float(svl_equal_tolerance_pct))
        self.allow_weak_structure = bool(allow_weak_structure)
        self.allow_equilibrium_overlapping_fvg = bool(allow_equilibrium_overlapping_fvg)
        if setup_max_age_hours < 1:
            raise ValueError("setup_max_age_hours must be >= 1")
        if m5_confirmation_mode not in {"CHOCH_ONLY", "CHOCH_OR_BOS", "BOS_AFTER_CHOCH"}:
            raise ValueError("m5_confirmation_mode must be CHOCH_ONLY, CHOCH_OR_BOS, or BOS_AFTER_CHOCH")
        self.setup_max_age_hours = int(setup_max_age_hours)
        self.m5_confirmation_mode = m5_confirmation_mode
        self.require_killzone = bool(require_killzone)
        self.require_displacement = bool(require_displacement)
        self.min_displacement_ratio = max(0.0, float(min_displacement_ratio))
        self.require_poi_confluence = bool(require_poi_confluence)

    def evaluate(self, h1_rows: list[dict[str, Any]], m5_rows: list[dict[str, Any]],
                 setup_state: dict[str, Any] | None = None,
                 h4_rows: list[dict[str, Any]] | None = None,
                 d1_rows: list[dict[str, Any]] | None = None) -> Decision:
        h1 = [Candle.from_dict(row) for row in h1_rows]
        m5 = [Candle.from_dict(row) for row in m5_rows]
        # H1 candles closing after the latest M5 close are outside this scan's
        # information set and cannot influence structure, POI, or target state.
        if m5:
            m5_open = _time_key(m5[-1].time)
            if isinstance(m5_open, datetime):
                cutoff = m5_open + timedelta(minutes=5)
                kept = [(row, candle) for row, candle in zip(h1_rows, h1)
                        if isinstance(_time_key(candle.time), datetime)
                        and _time_key(candle.time) + timedelta(hours=1) <= cutoff]
                h1_rows = [row for row, _ in kept]
                h1 = [candle for _, candle in kept]
        evidence: dict[str, Any] = {
            "timeframes": {"context": "1H", "execution": "M5"},
            "h1_structure": {}, "h1_dealing_range": {}, "h1_poi": {},
            "poi_state": {"poi_formed_time": None, "poi_touch_time": None,
                          "poi_active": False, "status": "UNIDENTIFIED",
                          "confirmation_invalidated": False,
                          "target_invalidated": False, "invalidated_at": None},
            "m5_liquidity": {"sweeps": [], "selected_sweep": None},
            "m5_confirmation": {},
            "displacement": {}, "stop": {}, "target": {}, "timing": {},
            "higher_timeframe": {},
        }
        if m5:
            try:
                timing = session_context(as_utc(m5[-1].time) + timedelta(minutes=5))
                evidence["timing"] = {
                    "timestamp_utc": timing.timestamp_utc, "session": timing.session,
                    "phase": timing.phase, "minutes_from_session_open": timing.minutes_from_session_open,
                    "london_active": timing.london_active,
                    "new_york_active": timing.new_york_active,
                    "overlap": timing.overlap, "required_gate": False,
                }
            except (TypeError, ValueError):
                evidence["timing"] = {"session": "UNKNOWN", "required_gate": False}
        if len(h1) < 20 or len(m5) < 20:
            return Decision("NO_TRADE", ["INSUFFICIENT_HISTORY"], evidence=evidence)

        h_structure = analyze_structure(h1, self.swing_left)
        evidence["h1_structure"] = h_structure
        m_structure = analyze_structure(m5, self.swing_left)
        evidence["svl"] = alignment_for_execution(
            h1_rows, m5_rows, self.swing_left, self.svl_profile_bins,
            self.svl_equal_tolerance_pct, h1_structure=h_structure,
            m5_structure=m_structure,
        )
        preliminary_confirmation = get_m5_execution_confirmation(
            m5, h_structure["side"], self.swing_left,
            structure=m_structure,
        )
        evidence["m5_confirmation"] = preliminary_confirmation.as_dict()
        side = h_structure["side"]
        if side is None:
            return Decision("NO_TRADE", ["H1_STRUCTURE_UNCLEAR"], evidence=evidence)
        evidence["higher_timeframe"] = build_higher_timeframe_context(
            h4_rows, d1_rows, side=side, current_price=float(m5[-1].close),
            swing_length=self.swing_left,
        )
        if (str(h_structure["state"]).endswith("_WEAK") and not self.allow_weak_structure):
            return Decision("NO_TRADE", ["H1_STRUCTURE_UNCLEAR"], side=side, evidence=evidence)

        if self.svl_require_alignment and not evidence["svl"]["aligned_for_trade"]:
            return Decision("NO_TRADE", ["SVL_NOT_ALIGNED"], side=side, evidence=evidence)

        low = h_structure["external_low"]
        high = h_structure["external_high"]
        if low is None or high is None or high <= low:
            return Decision("NO_TRADE", ["H1_DEALING_RANGE_UNAVAILABLE"], side=side, evidence=evidence)
        equilibrium = (low + high) / 2
        evidence["h1_dealing_range"] = {
            "low": low, "high": high, "equilibrium": equilibrium,
            "location": "DISCOUNT" if side == "LONG" else "PREMIUM",
            "low_index": h_structure["external_low_index"],
            "high_index": h_structure["external_high_index"],
        }

        poi = find_location_fvg(
            h1, side, low, high,
            allow_equilibrium_overlapping=self.allow_equilibrium_overlapping_fvg,
            after_index=h_structure["last_event"]["index"],
        )
        if poi is None:
            return Decision("NO_TRADE", ["H1_POI_NOT_FOUND_IN_LOCATION"], side=side, evidence=evidence)
        evidence["h1_poi"] = poi.as_dict()
        evidence["h1_poi_confluence"] = build_poi_confluence(
            h1, poi, side, low, high, h_structure["last_event"]["index"]
        )
        if self.require_poi_confluence and evidence["h1_poi_confluence"]["confluence_count"] < 2:
            return Decision("NO_TRADE", ["H1_POI_CONFLUENCE_INSUFFICIENT"], side=side, evidence=evidence)
        formed = _time_key(poi.time)
        observed = _time_key(m5[-1].time)
        if isinstance(formed, datetime) and isinstance(observed, datetime):
            age = observed + timedelta(minutes=5) - (formed + timedelta(hours=1))
            evidence["poi_state"]["age_hours"] = max(0.0, age.total_seconds() / 3600)
            evidence["poi_state"]["max_age_hours"] = self.setup_max_age_hours
            if age > timedelta(hours=self.setup_max_age_hours):
                evidence["poi_state"].update({"poi_formed_time": poi.time, "status": "EXPIRED"})
                return Decision("NO_TRADE", ["H1_SETUP_EXPIRED"], side=side, evidence=evidence)
        previous_setup_matches = bool(setup_state and _same_setup(setup_state, side, h_structure, poi))
        if previous_setup_matches and setup_state.get("status") == "CONFIRMED":
            evidence["poi_state"].update({
                "poi_formed_time": poi.time,
                "poi_touch_time": setup_state.get("poi_touch_time"),
                "poi_active": False,
                "status": "CONFIRMED",
                "prior_state_matched": True,
            })
            return Decision("NO_TRADE", ["SETUP_ALREADY_CONFIRMED"], side=side, evidence=evidence)
        prior_invalidation = (setup_state.get("invalidated_at")
                              if previous_setup_matches and setup_state.get("confirmation_invalidated")
                              else None)
        poi_touch = _first_poi_touch(m5, poi, h1_duration_minutes=60,
                                     after_time=prior_invalidation)
        poi_evidence = {
            "poi_formed_time": poi.time,
            "poi_touch_time": poi_touch["time"] if poi_touch else None,
            "poi_touch_index": poi_touch["index"] if poi_touch else None,
            "poi_active": poi_touch is not None,
            "status": "WAITING_FOR_M5_CONFIRMATION" if poi_touch else "WAITING_FOR_POI_TOUCH",
            "prior_state_matched": previous_setup_matches,
            "confirmation_invalidated": bool(prior_invalidation),
            "target_invalidated": False,
            "invalidated_at": prior_invalidation,
        }
        # Recover a persisted interaction only for an identical, still-current
        # structure/POI. A changed structure or POI cannot inherit an old touch.
        if previous_setup_matches and not prior_invalidation:
            stored_touch = setup_state.get("poi_touch_time")
            if stored_touch and _touch_is_after_formation(stored_touch, poi.time, 60):
                if poi_touch is None or _time_key(stored_touch) < _time_key(poi_touch["time"]):
                    poi_evidence.update({"poi_touch_time": stored_touch,
                                         "poi_touch_index": None,
                                         "poi_active": True,
                                         "status": "WAITING_FOR_M5_CONFIRMATION",
                                         "prior_state_matched": True})
        evidence["poi_state"] = poi_evidence
        if not poi_evidence["poi_active"]:
            reason = "POI_NOT_ACTIVE" if prior_invalidation else "PRICE_NOT_AT_H1_POI"
            return Decision("NO_TRADE", [reason], side=side, evidence=evidence)

        confirmation = get_m5_execution_confirmation(
            m5, side, self.swing_left, structure=m_structure,
        )
        evidence["m5_confirmation"] = confirmation.as_dict()
        if not confirmation.valid:
            if confirmation.reason_codes == ("M5_EVENT_DIRECTION_MISMATCH",):
                evidence["poi_state"].update({
                    "status": "CONFIRMATION_INVALIDATED",
                    "confirmation_invalidated": True,
                    "invalidated_at": confirmation.latest_event_time,
                })
            else:
                evidence["poi_state"]["status"] = "WAITING_FOR_M5_CONFIRMATION"
            return Decision("NO_TRADE", list(confirmation.reason_codes), side=side, evidence=evidence)
        touch_time = poi_evidence["poi_touch_time"]
        if _time_key(confirmation.latest_event_time) <= _time_key(touch_time):
            return Decision("NO_TRADE", ["M5_EVENT_PRECEDES_POI_TOUCH"], side=side, evidence=evidence)
        touch_index = poi_evidence["poi_touch_index"]
        if touch_index is None:
            touch_index = _index_after_time(m5, touch_time)
        if touch_index is None:
            return Decision("NO_TRADE", ["POI_NOT_ACTIVE"], side=side, evidence=evidence)

        sweeps = find_relevant_liquidity_sweeps(
            m5, m_structure, side, poi.bottom, poi.top,
            after_index=touch_index, max_age_bars=24,
        )
        event_index = confirmation.latest_event_index
        sweeps = [item for item in sweeps if item["index"] < event_index]
        evidence["m5_liquidity"] = {
            "required_type": "SELL_SIDE_SWEEP" if side == "LONG" else "BUY_SIDE_SWEEP",
            "sweeps": sweeps,
            "selected_sweep": sweeps[-1] if sweeps else None,
            "poi_relevant": bool(sweeps),
            "max_age_bars": 24,
        }
        if not sweeps:
            evidence["poi_state"]["status"] = "WAITING_FOR_LIQUIDITY_SWEEP"
            return Decision("NO_TRADE", ["M5_LIQUIDITY_SWEEP_NOT_CONFIRMED"], side=side, evidence=evidence)

        event = confirmation.latest_event
        assert event is not None
        preceding_events = [candidate for candidate in m_structure["events"]
                            if candidate["index"] < event["index"]]
        if self.m5_confirmation_mode == "CHOCH_ONLY":
            confirmation_type_ok = event["type"] == "CHOCH"
        elif self.m5_confirmation_mode == "BOS_AFTER_CHOCH":
            confirmation_type_ok = (event["type"] == "BOS" and any(
                candidate["type"] == "CHOCH" and candidate["side"] == side
                and candidate["index"] > sweeps[-1]["index"]
                for candidate in preceding_events))
        else:
            confirmation_type_ok = event["type"] in {"BOS", "CHOCH"}
        if not confirmation_type_ok:
            return Decision("NO_TRADE", ["M5_CONFIRMATION_TYPE_UNSUPPORTED"], side=side, evidence=evidence)
        if self.require_killzone and not in_kill_zone(confirmation.latest_event_time):
            evidence["timing"].update({"required_gate": True, "killzone_valid": False})
            return Decision("NO_TRADE", ["OUTSIDE_KILLZONE"], side=side, evidence=evidence)
        event_index = int(event["index"])
        candle = m5[event_index]
        atr = _atr(m5, event_index, 14)
        body = abs(candle.close - candle.open)
        displacement_ratio = body / atr if atr and atr > 0 else 0.0
        displacement = {
            "atr": atr, "body": body, "displacement_ratio": displacement_ratio,
            "displacement_valid": bool(atr and displacement_ratio >= self.min_displacement_ratio),
            "threshold": self.min_displacement_ratio, "normalization": "body / simple_mean_true_range_14",
            "required_gate": self.require_displacement,
        }
        evidence["displacement"] = displacement
        if self.require_displacement and not displacement["displacement_valid"]:
            return Decision("NO_TRADE", ["DISPLACEMENT_GATE_FAILED"], side=side, evidence=evidence)
        bodies = [abs(x.close - x.open) for x in m5[max(0, event_index - 10):event_index]
                  if x.close != x.open]
        median_body = median(bodies) if bodies else body
        legacy_body_ratio = body / median_body if median_body else 0.0
        bos = BosEvent(event_index, side, float(event["level"]), candle.close,
                       "STRONG" if displacement["displacement_valid"] else "NORMAL",
                       legacy_body_ratio, candle.time, str(event["type"]),
                       atr, body, displacement_ratio)
        evidence["m5_confirmation"].update({
            "accepted_types": ["CHOCH", "BOS"],
            "confirmation_mode": self.m5_confirmation_mode,
            "required_sequence": "sweep_then_current_same_direction_BOS_or_CHOCH",
            "sweep_index": sweeps[-1]["index"],
        })
        evidence["m5_bos"] = {
            "index": bos.index, "level": bos.level, "close": bos.close,
            "strength": bos.strength, "body_ratio": bos.body_ratio,
            "type": bos.event_type, "time": bos.time,
            "atr": bos.atr, "body": bos.body,
            "displacement_ratio": bos.displacement_ratio,
        }

        # The sweep candle's extreme is the local setup stop anchor. A post-sweep
        # confirmed opposite swing may refine it, but an unrelated distant H1
        # pivot is never silently substituted.
        sweep = sweeps[-1]
        sweep_candle = m5[sweep["index"]]
        post_sweep = [s for s in _swings_from_structure(m_structure)
                      if s.kind == ("LOW" if side == "LONG" else "HIGH")
                      and sweep["index"] <= s.index < event_index]
        if side == "LONG":
            local_anchor = min([sweep_candle.low] + [s.price for s in post_sweep])
            protected_price = (h_structure["protected_swing"]["price"]
                               if h_structure["protected_swing"] else None)
            stop_anchor = min(local_anchor, protected_price) if protected_price is not None else local_anchor
            stop_price = stop_anchor - self.stop_buffer
            target = h_structure["external_high_swing"]
            target_price = target["price"] if target else None
            target_index = target["index"] if target else None
            target_confirmed_index = target["confirmed_index"] if target else None
            entry_time = _time_key(m5[-1].time)
            entry_close_time = (entry_time + timedelta(minutes=5)
                                if isinstance(entry_time, datetime) else None)
            target_reached = bool(target and (
                _target_reached_before(h1, target_confirmed_index, "LONG", target_price, entry_close_time)
                or _target_reached_by_m5(m5, h1, target_confirmed_index,
                                         "LONG", target_price, entry_close_time)))
        else:
            local_anchor = max([sweep_candle.high] + [s.price for s in post_sweep])
            protected_price = (h_structure["protected_swing"]["price"]
                               if h_structure["protected_swing"] else None)
            stop_anchor = max(local_anchor, protected_price) if protected_price is not None else local_anchor
            stop_price = stop_anchor + self.stop_buffer
            target = h_structure["external_low_swing"]
            target_price = target["price"] if target else None
            target_index = target["index"] if target else None
            target_confirmed_index = target["confirmed_index"] if target else None
            entry_time = _time_key(m5[-1].time)
            entry_close_time = (entry_time + timedelta(minutes=5)
                                if isinstance(entry_time, datetime) else None)
            target_reached = bool(target and (
                _target_reached_before(h1, target_confirmed_index, "SHORT", target_price, entry_close_time)
                or _target_reached_by_m5(m5, h1, target_confirmed_index,
                                         "SHORT", target_price, entry_close_time)))
        entry = m5[-1].close
        stop_evidence = {
            "anchor": stop_anchor, "stop_anchor": stop_anchor,
            "price": stop_price, "stop_price": stop_price,
            "reason": "active_PoI_liquidity_sweep_extreme"
                     + ("_refined_by_post_sweep_confirmed_swing" if post_sweep else "")
                     + ("_combined_with_canonical_H1_protected_swing" if protected_price is not None else ""),
            "stop_reason": "active_PoI_liquidity_sweep_extreme"
                          + ("_refined_by_post_sweep_confirmed_swing" if post_sweep else "")
                          + ("_combined_with_canonical_H1_protected_swing" if protected_price is not None else ""),
            "local_anchor": local_anchor,
            "sweep_index": sweep["index"], "sweep_time": sweep["time"],
            "h1_protected_swing": h_structure["protected_swing"],
            "h1_protected_swing_used": bool(protected_price is not None and protected_price != local_anchor),
            "buffer": self.stop_buffer,
        }
        target_evidence = {
            "price": target_price, "index": target_index,
            "confirmed_index": target_confirmed_index,
            "time": target.get("time") if target else None,
            "type": (("EXTERNAL_LIQUIDITY_REACHED" if target_reached
                      else "UNTOUCHED_EXTERNAL_LIQUIDITY") if target else None),
            "already_reached_before_entry": target_reached,
            "source": "canonical_H1_external_swing",
        }
        evidence["stop"] = stop_evidence
        evidence["target"] = target_evidence
        # Legacy evidence names stay available to downstream diagnostics.
        evidence["m5_stop_swing"] = {"kind": "LOW" if side == "LONG" else "HIGH",
                                    "price": stop_anchor, "time": sweep["time"]}
        evidence["protected_stop_anchor"] = {
            "h1_price": (h_structure["protected_swing"]["price"]
                         if h_structure["protected_swing"] else None),
            "selected_price": stop_anchor, "buffer": self.stop_buffer,
        }
        evidence["h1_target"] = {"price": target_price, "index": target_index,
                                  "already_reached_before_entry": target_reached}
        if target_price is None:
            evidence["poi_state"].update({"status": "TARGET_INVALID", "target_invalidated": True})
            return Decision("NO_TRADE", ["H1_EXTERNAL_TARGET_UNAVAILABLE"], side=side, evidence=evidence)
        if target_reached:
            evidence["poi_state"].update({"status": "TARGET_REACHED", "target_invalidated": True})
            return Decision("NO_TRADE", ["H1_TARGET_ALREADY_REACHED"], side=side, evidence=evidence)
        risk = (entry - stop_price) if side == "LONG" else (stop_price - entry)
        reward = (target_price - entry) if side == "LONG" else (entry - target_price)
        if risk <= 0 or reward <= 0:
            evidence["poi_state"].update({"status": "INVALIDATED", "target_invalidated": True})
            return Decision("NO_TRADE", ["INVALID_RISK_GEOMETRY"], side=side, evidence=evidence)
        rr = reward / risk
        evidence["risk_reward"] = {"risk": risk, "reward": reward, "rr": rr, "minimum": self.min_rr}
        if rr < self.min_rr:
            evidence["poi_state"]["status"] = "INVALIDATED"
            return Decision("NO_TRADE", ["RISK_REWARD_BELOW_MINIMUM"], side=side, risk_reward=rr, evidence=evidence)
        evidence["poi_state"]["status"] = "CONFIRMED"
        return Decision("SIGNAL", [], side=side, entry_price=entry, stop_price=stop_price,
                        target_price=target_price, risk_reward=rr, evidence=evidence)


def _swings_from_structure(structure: dict[str, Any]) -> list[Swing]:
    result = []
    for kind in ("HIGH", "LOW"):
        values = structure.get("highs" if kind == "HIGH" else "lows", [])
        result.extend(Swing(int(item["index"]), kind, float(item["price"]), str(item["time"]))
                      for item in values)
    return sorted(result, key=lambda swing: swing.index)


def _time_key(value: str | None):
    if value is None:
        return None
    try:
        return as_utc(value)
    except (TypeError, ValueError):
        return str(value)


def _touch_is_after_formation(touch_time: str, formed_time: str, duration_minutes: int) -> bool:
    touch, formed = _time_key(touch_time), _time_key(formed_time)
    if not isinstance(touch, datetime) or not isinstance(formed, datetime):
        return False
    return touch >= formed + timedelta(minutes=duration_minutes)


def _same_setup(previous: dict[str, Any], side: Side, structure: dict[str, Any], poi: PointOfInterest) -> bool:
    if previous.get("status") in {"EXPIRED", "INVALIDATED", "TARGET_REACHED", "TARGET_INVALID"}:
        return False
    prior_structure = previous.get("h1_structure", {})
    prior_poi = previous.get("h1_poi", {})
    structural_keys = ("side", "state", "last_event", "protected_swing",
                       "external_high", "external_low", "external_high_index",
                       "external_low_index")
    structure_matches = all(prior_structure.get(key) == structure.get(key)
                            for key in structural_keys)
    return (previous.get("side") == side
            and structure_matches
            and prior_poi.get("time") == poi.time
            and prior_poi.get("bottom") == poi.bottom
            and prior_poi.get("top") == poi.top)


def _index_after_time(candles: list[Candle], value: str) -> int | None:
    key = _time_key(value)
    for index, candle in enumerate(candles):
        current = _time_key(candle.time)
        if current is not None and current >= key:
            return index
    return None


def _target_reached_before(candles: list[Candle], target_index: int | None,
                           side: Side, target_price: float,
                           entry_close_time: datetime | None) -> bool:
    if target_index is None:
        return False
    for candle in candles[target_index + 1:]:
        opened = _time_key(candle.time)
        if isinstance(entry_close_time, datetime) and isinstance(opened, datetime):
            if opened + timedelta(hours=1) > entry_close_time:
                continue
        if side == "LONG" and candle.high >= target_price:
            return True
        if side == "SHORT" and candle.low <= target_price:
            return True
    return False


def _target_reached_by_m5(m5: list[Candle], h1: list[Candle],
                          target_confirmed_index: int | None, side: Side,
                          target_price: float,
                          entry_close_time: datetime | None) -> bool:
    if (target_confirmed_index is None or target_confirmed_index >= len(h1)
            or not isinstance(entry_close_time, datetime)):
        return False
    confirmed_open = _time_key(h1[target_confirmed_index].time)
    if not isinstance(confirmed_open, datetime):
        return False
    target_known_time = confirmed_open + timedelta(hours=1)
    for candle in m5:
        opened = _time_key(candle.time)
        if not isinstance(opened, datetime):
            continue
        closed = opened + timedelta(minutes=5)
        if opened < target_known_time or closed > entry_close_time:
            continue
        if side == "LONG" and candle.high >= target_price:
            return True
        if side == "SHORT" and candle.low <= target_price:
            return True
    return False


def _first_poi_touch(candles: list[Candle], poi: PointOfInterest,
                     h1_duration_minutes: int,
                     after_time: str | None = None) -> dict[str, Any] | None:
    formed_close = _time_key(poi.time)
    if not hasattr(formed_close, "__add__"):
        return None
    formed_close += timedelta(minutes=h1_duration_minutes)
    for index, candle in enumerate(candles):
        candle_time = _time_key(candle.time)
        # M5 open must be at/after the H1 formation close. Same-H1-bar overlap
        # is not treated as a retest because intrabar ordering is unknowable.
        if candle_time < formed_close:
            continue
        if after_time and candle_time <= _time_key(after_time):
            continue
        if poi.overlaps(candle):
            return {"index": index, "time": candle.time,
                    "price_low": candle.low, "price_high": candle.high}
    return None


def _atr(candles: list[Candle], index: int, period: int = 14) -> float | None:
    if index < 0 or not candles:
        return None
    start = max(0, index - period + 1)
    ranges = []
    for i in range(start, index + 1):
        candle = candles[i]
        previous_close = candles[i - 1].close if i > 0 else candle.close
        ranges.append(max(candle.high - candle.low,
                          abs(candle.high - previous_close),
                          abs(candle.low - previous_close)))
    return sum(ranges) / len(ranges) if ranges else None


def find_location_fvg(candles: list[Candle], side: Side, low: float, high: float,
                      allow_equilibrium_overlapping: bool = True,
                      after_index: int | None = None) -> PointOfInterest | None:
    midpoint = (low + high) / 2
    candidates: list[PointOfInterest] = []
    for i in range(2, len(candles)):
        if after_index is not None and i < after_index:
            continue
        one, three = candles[i - 2], candles[i]
        if side == "LONG" and three.low > one.high:
            bottom, top = one.high, three.low
            location_ok = bottom <= midpoint if allow_equilibrium_overlapping else top <= midpoint
            if location_ok and not any(c.close <= bottom for c in candles[i + 1:]):
                candidates.append(PointOfInterest("FVG", side, bottom, top, i, three.time))
        elif side == "SHORT" and three.high < one.low:
            bottom, top = three.high, one.low
            location_ok = top >= midpoint if allow_equilibrium_overlapping else bottom >= midpoint
            if location_ok and not any(c.close >= top for c in candles[i + 1:]):
                candidates.append(PointOfInterest("FVG", side, bottom, top, i, three.time))
    return candidates[-1] if candidates else None


def find_swings(candles: list[Candle], left: int = 2, right: int = 2) -> list[Swing]:
    """Compatibility wrapper for confirmed pivots (left/right must match)."""
    if left != right:
        raise ValueError("causal swing detection requires matching left and right lengths")
    from .structure import find_swing_highs, find_swing_lows
    return sorted(find_swing_highs(candles, left) + find_swing_lows(candles, left),
                  key=lambda swing: swing.index)


def dealing_range(swings: list[Swing], side: Side) -> tuple[float, float] | None:
    highs = [s.price for s in swings if s.kind == "HIGH"]
    lows = [s.price for s in swings if s.kind == "LOW"]
    if not highs or not lows:
        return None
    low, high = lows[-1], highs[-1]
    return (low, high) if high > low else None


def find_latest_bos(candles: list[Candle], swings: list[Swing], side: Side,
                    swing_length: int = 3,
                    confirmation: M5ExecutionConfirmation | None = None) -> BosEvent | None:
    del swings  # Canonical structure owns swing detection and event selection.
    confirmation = confirmation or get_m5_execution_confirmation(candles, side, swing_length)
    if not confirmation.valid or confirmation.latest_event is None:
        return None
    event = confirmation.latest_event
    index = int(event["index"])
    candle = candles[index]
    body = abs(candle.close - candle.open)
    previous = [abs(x.close - x.open) for x in candles[max(0, index - 10):index]
                if x.close != x.open]
    median_body = median(previous) if previous else body
    ratio = body / median_body if median_body else 0.0
    atr = _atr(candles, index, 14)
    displacement_ratio = body / atr if atr else 0.0
    strength = "STRONG" if displacement_ratio >= 1.0 else "NORMAL"
    return BosEvent(index, side, event["level"], candle.close, strength, ratio,
                    candle.time, event["type"], atr, body, displacement_ratio)


def latest_opposite_swing(swings: list[Swing], before_index: int, side: Side) -> Swing | None:
    kind = "LOW" if side == "LONG" else "HIGH"
    options = [s for s in swings if s.kind == kind and s.index < before_index]
    return options[-1] if options else None
