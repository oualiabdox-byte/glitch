#!/usr/bin/env python3
"""Closed-bar cTrader signal scan using the bleach H1/M5 strategy.

This process is signal-only. It never submits orders; demo execution remains
isolated behind execution.demo_order and execution.demo_guard.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone

from config.settings import (load_config, pairs as configured_pairs,
                             risk_config, strategy_config)
from data.ctrader import CTraderData
from strategy import build_variant, select_signals, signal_identity, variants_for_pair
from strategy import safety


def _closed(candles, minutes: int, now: datetime):
    result = []
    for candle in candles:
        opened = datetime.fromisoformat(str(candle["time"]).replace("Z", "+00:00")).astimezone(timezone.utc)
        if opened + timedelta(minutes=minutes) <= now:
            result.append(candle)
    return result


def _freshness_check(h1, m5, now: datetime, max_quote_age_seconds: int) -> dict:
    """Reject a scan only after the expected latest closed bar misses its grace period.

    The configured age is a grace period after the next scheduled H1/M5 close,
    not the raw age of an H1 close (which would incorrectly reject most of each
    hour). This lets the provider return the most recent completed bar while
    rejecting a feed that remains behind after the configured delay.
    """
    now = now.astimezone(timezone.utc)
    frames = (("h1", h1, 60), ("m5", m5, 5))
    result = {"max_quote_age_seconds": max_quote_age_seconds, "frames": {}}
    for name, candles, minutes in frames:
        period_seconds = minutes * 60
        expected_epoch = int(now.timestamp() // period_seconds) * period_seconds
        expected_close = datetime.fromtimestamp(expected_epoch, tz=timezone.utc)
        latest = max(
            candles,
            key=lambda row: datetime.fromisoformat(
                str(row["time"]).replace("Z", "+00:00")).astimezone(timezone.utc),
        ) if candles else None
        if latest is None:
            result["frames"][name] = {
                "fresh": False, "reason": f"NO_{name.upper()}_CANDLES",
                "expected_latest_close_utc": expected_close.isoformat(),
            }
            continue
        opened = datetime.fromisoformat(
            str(latest["time"]).replace("Z", "+00:00")).astimezone(timezone.utc)
        closed_at = opened + timedelta(minutes=minutes)
        grace_elapsed = max(0.0, (now - expected_close).total_seconds())
        behind_seconds = max(0.0, (expected_close - closed_at).total_seconds())
        stale = closed_at < expected_close and grace_elapsed > max_quote_age_seconds
        result["frames"][name] = {
            "fresh": not stale,
            "reason": f"STALE_{name.upper()}_DATA" if stale else None,
            "latest_open_utc": opened.isoformat(),
            "latest_close_utc": closed_at.isoformat(),
            "expected_latest_close_utc": expected_close.isoformat(),
            "age_seconds": max(0.0, (now - closed_at).total_seconds()),
            "behind_expected_seconds": behind_seconds,
            "grace_elapsed_seconds": grace_elapsed,
            "max_quote_age_seconds": max_quote_age_seconds,
        }
    result["fresh"] = all(frame["fresh"] for frame in result["frames"].values())
    result["reason_codes"] = [frame["reason"] for frame in result["frames"].values()
                               if frame.get("reason")]
    return result


def _market_snapshot(pair: str, cfg: dict, end: datetime) -> dict:
    start = end - timedelta(days=int(os.getenv("CTRADER_LOOKBACK_DAYS", "30")))
    feed = CTraderData()
    data = feed.download(pair, start, end, periods=("h1", "m5"))
    return {"pair": pair, "cfg": cfg, "scan_time": end,
            "h1": _closed(data["h1"], 60, end),
            "m5": _closed(data["m5"], 5, end)}


def scan(pair: str, setup_state: dict | None = None, variant_name: str | None = None,
         market_snapshot: dict | None = None):
    variant_name = variant_name or "config_default"
    if variant_name != "config_default" and variant_name not in variants_for_pair(pair):
        raise ValueError(f"variant {variant_name!r} is not registered for {pair!r}")
    snapshot = market_snapshot
    if snapshot is None:
        cfg = load_config()
        end = datetime.now(timezone.utc)
        snapshot = _market_snapshot(pair, cfg, end)
    cfg = snapshot["cfg"]
    end = snapshot["scan_time"]
    h1 = snapshot["h1"]
    m5 = snapshot["m5"]

    max_quote_age_seconds = risk_config(cfg)["max_quote_age_seconds"]
    freshness = _freshness_check(h1, m5, end, max_quote_age_seconds)
    if not freshness["fresh"]:
        return {"pair": pair, "variant": variant_name, "status": "NO_TRADE",
                "reason_codes": freshness["reason_codes"],
                "h1_closed": len(h1), "m5_closed": len(m5),
                "data_freshness": freshness,
                "data_source": "cTrader Open API"}
    if len(h1) < 20 or len(m5) < 20:
        return {"pair": pair, "variant": variant_name, "status": "NO_TRADE",
                "reason_codes": ["INSUFFICIENT_CLOSED_DATA"],
                "h1_closed": len(h1), "m5_closed": len(m5),
                "data_freshness": freshness,
                "data_source": "cTrader Open API"}

    latest = m5[-1]
    signal_close = datetime.fromisoformat(str(latest["time"]).replace("Z", "+00:00")).astimezone(timezone.utc) + timedelta(minutes=5)
    max_atr_spike = float(os.getenv("CTRADER_MAX_ATR_SPIKE", cfg.get("safety", {}).get("max_atr_spike", 2.5)))
    news_before = int(os.getenv("CTRADER_NEWS_PAUSE_BEFORE_MIN", "45"))
    news_after = int(os.getenv("CTRADER_NEWS_PAUSE_AFTER_MIN", "20"))
    news_events = safety.load_news_events(os.getenv("CTRADER_NEWS_EVENTS_JSON", ""))

    if safety.abnormal_volatility(h1, max_ratio=max_atr_spike):
        return {"pair": pair, "variant": variant_name, "status": "NO_TRADE", "reason_codes": ["ABNORMAL_VOLATILITY"],
                "signal_close_utc": signal_close.isoformat(), "data_source": "cTrader Open API"}
    if safety.news_blocked(signal_close, pair, news_events, pause_before_minutes=news_before, pause_after_minutes=news_after):
        return {"pair": pair, "variant": variant_name, "status": "NO_TRADE", "reason_codes": ["NEWS_BLACKOUT"],
                "signal_close_utc": signal_close.isoformat(), "data_source": "cTrader Open API"}

    resolved = strategy_config(cfg)
    strategy = build_variant(variant_name, base_options=resolved)
    decision = strategy.evaluate(h1, m5, setup_state=setup_state)
    evidence = decision.evidence
    structure = evidence.get("h1_structure", {})
    poi = evidence.get("h1_poi", {})
    poi_lifecycle = evidence.get("poi_state", {})
    setup_snapshot = None
    if structure.get("side") and structure.get("last_event") and poi:
        setup_snapshot = {
            "side": structure["side"], "h1_structure": structure,
            "h1_poi": poi, "poi_formed_time": poi_lifecycle.get("poi_formed_time"),
            "poi_touch_time": poi_lifecycle.get("poi_touch_time"),
            "poi_active": poi_lifecycle.get("poi_active", False),
            "confirmation_invalidated": poi_lifecycle.get("confirmation_invalidated", False),
            "target_invalidated": poi_lifecycle.get("target_invalidated", False),
            "invalidated_at": poi_lifecycle.get("invalidated_at"),
            "status": poi_lifecycle.get("status", "IDENTIFIED"),
            "updated_at": signal_close.isoformat(),
        }
    base = {"pair": pair, "variant": variant_name, "data_source": "cTrader Open API", "signal_close_utc": signal_close.isoformat(),
            "h1_closed": len(h1), "m5_closed": len(m5), "reason_codes": decision.reason_codes,
            "evidence": evidence, "setup_state": setup_snapshot,
            "data_freshness": freshness}
    if not decision.is_signal:
        return {**base, "status": "NO_TRADE"}
    signal = {**base, "status": "SIGNAL_ONLY", "side": decision.side,
              "entry_price": decision.entry_price, "stop_price": decision.stop_price,
              "target_price": decision.target_price, "tp_target": decision.target_price,
              "rr": decision.risk_reward, "timestamp": signal_close.isoformat()}
    signal["signal_id"] = signal_identity(signal)
    return signal


def scan_pair(pair: str, setup_states: dict | None = None) -> dict:
    """Fetch one snapshot; evaluate every variant before selecting any signal."""
    variant_names = variants_for_pair(pair) or ("config_default",)
    states = setup_states if isinstance(setup_states, dict) else {}
    try:
        cfg = load_config()
        snapshot = _market_snapshot(pair, cfg, datetime.now(timezone.utc))
    except Exception as exc:
        results = [{"pair": pair, "variant": name, "status": "ERROR", "error": str(exc)}
                   for name in variant_names]
        return {"pair": pair, "variant_results": results,
                "selection": select_signals(results, expected_variants=variant_names)}
    results = []
    for name in variant_names:
        try:
            results.append(scan(pair, setup_state=states.get(name), variant_name=name,
                                market_snapshot=snapshot))
        except Exception as exc:
            results.append({"pair": pair, "variant": name, "status": "ERROR", "error": str(exc)})
    selection = select_signals(results, expected_variants=variant_names)
    return {"pair": pair, "variant_results": results, "selection": selection}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair", help="scan one pair instead of all configured pairs")
    args = parser.parse_args()
    cfg = load_config()
    pairs = [args.pair.upper()] if args.pair else [p.strip().upper() for p in os.getenv("CTRADER_PAIRS", ",".join(configured_pairs(cfg))).split(",") if p.strip()]
    print("=== H1/M5 CANONICAL STRATEGY / cTrader ===")
    print("Order submission: DISABLED")
    for pair in pairs:
        try:
            raw_state = os.getenv("CTRADER_SETUP_STATE_JSON")
            parsed_state = json.loads(raw_state) if raw_state else {}
            if not isinstance(parsed_state, dict):
                parsed_state = {}
        except json.JSONDecodeError:
            parsed_state = {}
        variant_names = variants_for_pair(pair) or ("config_default",)
        if len(variant_names) == 1 and pair in parsed_state:
            parsed_state.setdefault(variant_names[0], parsed_state[pair])
        batch = scan_pair(pair, setup_states=parsed_state)
        for result in batch["variant_results"]:
            print(json.dumps(result, sort_keys=True))
        print(json.dumps({"event": "signal_selection", "pair": pair,
                          **batch["selection"]}, sort_keys=True))


if __name__ == "__main__":
    main()
