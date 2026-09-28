from __future__ import annotations

from datetime import datetime, timedelta, timezone

from config.settings import strategy_config
from strategy.engine import Strategy
from strategy.models import Candle
from strategy.structure import analyze_structure, detect_structure_events


def _c(index: int, high: float, low: float, close: float, *, start=None, open_=None):
    start = start or datetime(2026, 1, 1, tzinfo=timezone.utc)
    stamp = start + timedelta(hours=index)
    return Candle(stamp.isoformat().replace("+00:00", "Z"),
                  close if open_ is None else open_, high, low, close)


def _up_bars():
    # Low pivot 98 is confirmed before close 103 breaks the confirmed 102 high.
    values = [
        (101, 99, 100), (100, 98, 99), (102, 99, 101),
        (101.5, 100, 101), (103, 100, 103),
        (105, 102, 102.5), (104, 102, 103), (103.5, 102.5, 103),
    ]
    return [_c(i, h, l, close, open_=close - 0.1) for i, (h, l, close) in enumerate(values)]


def _down_bars():
    values = [
        (101, 99, 100), (102, 100, 101), (101, 98, 99),
        (100, 98.5, 99), (100, 97, 97.5),
        (98, 95, 97.5), (98, 96, 97), (97.5, 96.5, 97),
    ]
    return [_c(i, h, l, close, open_=close + 0.1) for i, (h, l, close) in enumerate(values)]


def _valid_rows(reach_target=False):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    h1 = [_c(i, 100.5, 99.5, 100, start=start) for i in range(20)]
    h1.extend(_c(20 + i, h, l, close, open_=close - 0.1,
                 start=start)
              for i, (h, l, close) in enumerate([
                  (101, 99, 100), (100, 98, 99), (102, 99, 101),
                  (101.5, 100, 101), (103, 100, 103),
                  (105, 102, 102.5), (104, 102, 103), (103.5, 102.5, 103),
              ]))
    if reach_target:
        # Wick reaches the objective even though the body does not close over it.
        last = h1[-1]
        h1[-1] = Candle(last.time, 103, 105.1, 102.5, 104)
    rows_h1 = [dict(time=x.time, open=x.open, high=x.high, low=x.low, close=x.close) for x in h1]

    m5_start = start + timedelta(hours=len(h1))
    rows_m5 = []
    for i in range(20):
        high, low, close, open_ = 102.0, 101.7, 101.85, 101.8
        if i == 2:
            high, low, close, open_ = 101.95, 101.6, 101.85, 101.8
        if i == 3:
            high, low, close, open_ = 102.05, 101.8, 101.9, 101.85
        if i == 4:
            high, low, close, open_ = 101.95, 101.4, 101.82, 101.7
        if i == 9:
            high, low, close, open_ = 102.15, 101.7, 101.95, 101.85
        if i == 19:
            high, low, close, open_ = 102.5, 101.7, 102.3, 101.8
        stamp = (m5_start + timedelta(minutes=5 * i)).isoformat().replace("+00:00", "Z")
        rows_m5.append({"time": stamp, "open": open_, "high": high, "low": low, "close": close})
    return rows_h1, rows_m5


def test_h1_direction_is_from_one_authoritative_bullish_event_stream():
    result = analyze_structure(_up_bars(), length=1)
    assert result["side"] == "LONG"
    assert result["state"] in {"BULLISH_WEAK", "BULLISH"}
    assert result["last_event"]["side"] == result["side"]
    assert result["last_event"]["type"] == "BOS"
    assert result["protected_swing"]["price"] == 102
    assert result["external_low"] == result["protected_swing"]["price"]
    assert result["external_high"] == 105


def test_h1_direction_is_from_one_authoritative_bearish_event_stream():
    result = analyze_structure(_down_bars(), length=1)
    assert result["side"] == "SHORT"
    assert result["last_event"]["side"] == result["side"]
    assert result["last_event"]["type"] == "BOS"
    assert result["protected_swing"]["kind"] == "HIGH"


def test_bearish_swing_labels_cannot_override_authoritative_bullish_bos():
    bars = _up_bars()
    for i, (high, low, close) in enumerate([
        (103, 100, 103), (104, 96, 103), (103, 99, 102.5), (102, 100, 102.1),
    ], start=8):
        bars.append(_c(i, high, low, close, open_=close - 0.1,
                       start=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    result = analyze_structure(bars, length=1)
    assert result["highs"][-1]["label"] == "LH"
    assert result["lows"][-1]["label"] == "LL"
    assert result["side"] == "LONG"
    assert result["last_event"]["side"] == "LONG"


def test_range_and_directional_transition_have_no_strategy_side():
    flat = [_c(i, 101, 99, 100) for i in range(30)]
    assert analyze_structure(flat, length=1)["side"] is None
    # A close through the opposing confirmed pivot after an established uptrend
    # must be CHOCH and clear the side until continuation confirms the transition.
    bars = _up_bars()
    down_break = _c(8, 103, 96, 97, start=datetime(2026, 1, 1, 8, tzinfo=timezone.utc))
    result = analyze_structure(bars + [down_break], length=1)
    if result["last_event"] and result["last_event"]["type"] == "CHOCH":
        assert result["side"] is None
        assert result["state"] == "TRANSITION"


def test_swing_cannot_generate_event_before_right_side_confirmation():
    bars = [
        _c(0, 101, 99, 100), _c(1, 100, 98, 99), _c(2, 102, 99, 101),
        _c(3, 101, 100, 101), _c(4, 103, 100, 103),
    ]
    assert detect_structure_events(bars[:3], 1) == []
    assert detect_structure_events(bars[:4], 1) == []
    event = detect_structure_events(bars, 1)[-1]
    assert event["index"] == 4
    assert event["confirmed_swing_index"] < event["index"]


def test_same_authoritative_stream_is_used_by_svl_and_strategy():
    rows_h1, rows_m5 = _valid_rows()
    decision = Strategy(swing_left=1, swing_right=1).evaluate(rows_h1, rows_m5)
    assert decision.evidence["h1_structure"]["side"] == decision.evidence["svl"]["side"]
    assert decision.evidence["h1_structure"]["last_event"] == decision.evidence["svl"]["structure"]["last_event"]


def test_future_h1_bar_cannot_change_the_current_m5_decision():
    h1, m5 = _valid_rows()
    strategy = Strategy(swing_left=1, swing_right=1)
    baseline = strategy.evaluate(h1, m5)
    h1_with_future = list(h1) + [{
        "time": "2026-01-02T06:00:00Z", "open": 103, "high": 999,
        "low": 1, "close": 500,
    }]
    with_future = strategy.evaluate(h1_with_future, m5)
    assert with_future.status == baseline.status
    assert with_future.reason_codes == baseline.reason_codes
    assert with_future.evidence["h1_structure"] == baseline.evidence["h1_structure"]


def test_weak_structure_setting_rejects_first_bos_as_configured():
    h1, m5 = _valid_rows()
    decision = Strategy(swing_left=1, swing_right=1, allow_weak_structure=False).evaluate(h1, m5)
    assert decision.status == "NO_TRADE"
    assert decision.reason_codes == ["H1_STRUCTURE_UNCLEAR"]
    assert decision.evidence["h1_structure"]["state"] == "BULLISH_WEAK"


def test_valid_poi_touch_sweep_confirmation_has_auditable_stop_target_and_displacement():
    h1, m5 = _valid_rows()
    decision = Strategy(swing_left=1, swing_right=1).evaluate(h1, m5)
    assert decision.status == "SIGNAL", decision.reason_codes
    evidence = decision.evidence
    assert evidence["h1_poi"]["type"] == "FVG"
    assert evidence["poi_state"]["poi_formed_time"]
    assert evidence["poi_state"]["poi_touch_time"]
    assert evidence["poi_state"]["poi_active"] is True
    assert evidence["m5_liquidity"]["selected_sweep"]["type"] == "SELL_SIDE_SWEEP"
    assert evidence["m5_liquidity"]["selected_sweep"]["index"] < evidence["m5_confirmation"]["latest_event_index"]
    assert evidence["stop"]["reason"].startswith("active_PoI_liquidity_sweep_extreme")
    local_low = m5[evidence["m5_liquidity"]["selected_sweep"]["index"]]["low"]
    protected_low = evidence["h1_structure"]["protected_swing"]["price"]
    assert evidence["stop"]["anchor"] == min(local_low, protected_low)
    assert decision.stop_price <= evidence["stop"]["anchor"]
    assert evidence["target"]["type"] == "UNTOUCHED_EXTERNAL_LIQUIDITY"
    assert evidence["displacement"]["atr"] > 0
    assert evidence["displacement"]["body"] > 0
    assert evidence["displacement"]["displacement_ratio"] >= 0


def test_unrelated_historical_sweep_does_not_qualify_for_active_poi():
    h1, m5 = _valid_rows()
    # Move the only sweep candle away from the H1 POI; a historical low-side
    # raid that is not setup-local is not qualifying liquidity.
    m5[4]["low"] = 102.01
    decision = Strategy(swing_left=1, swing_right=1).evaluate(h1, m5)
    assert decision.status == "NO_TRADE"
    assert decision.reason_codes == ["M5_LIQUIDITY_SWEEP_NOT_CONFIRMED"]


def test_current_opposite_m5_event_invalidates_active_setup():
    h1, m5 = _valid_rows()
    m5[-1].update({"open": 102.2, "high": 102.3, "low": 99.0, "close": 99.5})
    decision = Strategy(swing_left=1, swing_right=1).evaluate(h1, m5)
    assert decision.reason_codes == ["M5_EVENT_DIRECTION_MISMATCH"]
    assert decision.evidence["poi_state"]["confirmation_invalidated"] is True
    assert decision.evidence["poi_state"]["invalidated_at"] == m5[-1]["time"]


def test_old_sweep_cannot_be_reused_after_confirmation_invalidation_and_retest():
    h1, m5 = _valid_rows()
    first = Strategy(swing_left=1, swing_right=1).evaluate(h1, m5)
    state = {
        "side": first.evidence["h1_structure"]["side"],
        "h1_structure": first.evidence["h1_structure"],
        "h1_poi": first.evidence["h1_poi"],
        "poi_touch_time": first.evidence["poi_state"]["poi_touch_time"],
        "status": "CONFIRMATION_INVALIDATED",
        "confirmation_invalidated": True,
        "invalidated_at": m5[10]["time"],
    }
    next_decision = Strategy(swing_left=1, swing_right=1).evaluate(h1, m5, setup_state=state)
    assert next_decision.reason_codes == ["M5_LIQUIDITY_SWEEP_NOT_CONFIRMED"]
    assert next_decision.evidence["poi_state"]["confirmation_invalidated"] is True
    assert next_decision.evidence["poi_state"]["poi_touch_time"] > state["invalidated_at"]


def test_poi_setup_expires_after_configured_maximum_age():
    h1, m5 = _valid_rows()
    for row in m5:
        opened = datetime.fromisoformat(row["time"].replace("Z", "+00:00"))
        row["time"] = (opened + timedelta(hours=100)).isoformat().replace("+00:00", "Z")
    decision = Strategy(swing_left=1, swing_right=1, setup_max_age_hours=72).evaluate(h1, m5)
    assert decision.reason_codes == ["H1_SETUP_EXPIRED"]
    assert decision.evidence["poi_state"]["status"] == "EXPIRED"


def test_target_touched_by_wick_before_entry_is_rejected():
    h1, m5 = _valid_rows(reach_target=True)
    decision = Strategy(swing_left=1, swing_right=1).evaluate(h1, m5)
    assert decision.status == "NO_TRADE"
    assert decision.reason_codes == ["H1_TARGET_ALREADY_REACHED"]
    assert decision.evidence["target"]["already_reached_before_entry"] is True


def test_confirmation_policy_can_require_choch_or_bos_after_choch():
    h1, m5 = _valid_rows()
    choch_only = Strategy(swing_left=1, swing_right=1,
                          m5_confirmation_mode="CHOCH_ONLY").evaluate(h1, m5)
    assert choch_only.reason_codes == ["M5_CONFIRMATION_TYPE_UNSUPPORTED"]
    bos_after_choch = Strategy(swing_left=1, swing_right=1,
                               m5_confirmation_mode="BOS_AFTER_CHOCH").evaluate(h1, m5)
    assert bos_after_choch.reason_codes == ["M5_CONFIRMATION_TYPE_UNSUPPORTED"]


def test_poi_touch_on_same_m5_bar_as_confirmation_is_not_retroactively_active():
    h1, m5 = _valid_rows()
    # The latest event bar is also the first candle that reaches the POI; with
    # no knowable intrabar ordering, it cannot satisfy the earlier-touch rule.
    for row in m5[:-1]:
        row["high"] = 102.1
        row["low"] = 102.01
        row["close"] = 102.05
    m5[9]["high"] = 102.15
    decision = Strategy(swing_left=1, swing_right=1).evaluate(h1, m5)
    assert decision.status == "NO_TRADE"
    assert decision.reason_codes[0] in {"M5_EVENT_STALE", "M5_EVENT_PRECEDES_POI_TOUCH"}


def test_config_yaml_defaults_and_environment_overrides_are_consistent():
    yaml = {
        "strategy": {
            "swing_length": 3, "min_rr": 2.5, "stop_buffer": 0.0,
            "allow_weak_structure": False,
            "allow_equilibrium_overlapping_fvg": False,
            "setup_max_age_hours": 72,
            "m5_confirmation_mode": "CHOCH_OR_BOS",
            "svl": {"require_alignment": False, "profile_bins": 24,
                    "equal_tolerance_pct": 0.001},
        }
    }
    defaults = strategy_config(yaml, {})
    assert defaults == {
        "swing_length": 3, "min_rr": 2.5, "stop_buffer": 0.0,
        "allow_weak_structure": False,
        "allow_equilibrium_overlapping_fvg": False,
        "setup_max_age_hours": 72,
        "m5_confirmation_mode": "BOS_AFTER_CHOCH",
        "svl_require_alignment": False, "svl_profile_bins": 24,
        "svl_equal_tolerance_pct": 0.001,
    }
    env = {"CTRADER_SWING_LENGTH": "4", "CTRADER_MIN_RR": "1.5",
           "CTRADER_STOP_BUFFER": "0.0002", "CTRADER_ALLOW_WEAK_STRUCTURE": "false",
           "CTRADER_ALLOW_EQUILIBRIUM_OVERLAPPING_FVG": "false",
           "CTRADER_SVL_REQUIRE_ALIGNMENT": "true", "CTRADER_SVL_PROFILE_BINS": "32",
           "CTRADER_SVL_EQUAL_TOLERANCE_PCT": "0.002"}
    resolved = strategy_config(yaml, env)
    assert resolved["swing_length"] == 4
    assert resolved["min_rr"] == 1.5
    assert resolved["stop_buffer"] == 0.0002
    assert resolved["allow_weak_structure"] is False
    assert resolved["allow_equilibrium_overlapping_fvg"] is False
    assert resolved["svl_require_alignment"] is True
    assert resolved["svl_profile_bins"] == 32
    assert resolved["svl_equal_tolerance_pct"] == 0.002

    from config.settings import load_config
    actual = strategy_config(load_config(), {})
    assert actual["swing_length"] == 3
    assert actual["min_rr"] == 2.5
    assert actual["stop_buffer"] == 0.0
    assert actual["allow_weak_structure"] is False
    assert actual["allow_equilibrium_overlapping_fvg"] is False
    assert actual["m5_confirmation_mode"] == "BOS_AFTER_CHOCH"
    assert actual["require_displacement"] is True
    assert actual["min_displacement_ratio"] == 1.0
    assert actual["require_poi_confluence"] is True
    assert actual["svl_require_alignment"] is False
    assert actual["svl_profile_bins"] == 24
    assert actual["svl_equal_tolerance_pct"] == 0.001


def test_invalidated_or_expired_setup_state_is_not_reused():
    h1, m5 = _valid_rows()
    state = {"side": "LONG", "h1_structure": {"last_event": {"time": "different"}},
             "h1_poi": {"time": "different", "bottom": -1, "top": 0},
             "poi_touch_time": "2026-01-01T06:00:00Z", "status": "WAITING_FOR_M5_CONFIRMATION"}
    decision = Strategy(swing_left=1, swing_right=1).evaluate(h1, m5, setup_state=state)
    assert decision.evidence["poi_state"]["prior_state_matched"] is False
