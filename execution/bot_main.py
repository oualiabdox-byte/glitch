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

from config.settings import load_config, pairs as configured_pairs, strategy_config
from data.ctrader import CTraderData
from strategy import Strategy
from strategy import safety, timing


def _closed(candles, minutes: int, now: datetime):
    result = []
    for candle in candles:
        opened = datetime.fromisoformat(str(candle["time"]).replace("Z", "+00:00")).astimezone(timezone.utc)
        if opened + timedelta(minutes=minutes) <= now:
            result.append(candle)
    return result


def scan(pair: str, setup_state: dict | None = None):
    cfg = load_config()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=int(os.getenv("CTRADER_LOOKBACK_DAYS", "30")))
    feed = CTraderData()
    data = feed.download(pair, start, end, periods=("h1", "m5"))
    h1 = _closed(data["h1"], 60, end)
    m5 = _closed(data["m5"], 5, end)

    if len(h1) < 20 or len(m5) < 20:
        return {"pair": pair, "status": "NO_TRADE", "reason_codes": ["INSUFFICIENT_CLOSED_DATA"],
                "h1_closed": len(h1), "m5_closed": len(m5), "data_source": "cTrader Open API"}

    latest = m5[-1]
    signal_close = datetime.fromisoformat(str(latest["time"]).replace("Z", "+00:00")).astimezone(timezone.utc) + timedelta(minutes=5)
    max_atr_spike = float(os.getenv("CTRADER_MAX_ATR_SPIKE", cfg.get("safety", {}).get("max_atr_spike", 2.5)))
    news_before = int(os.getenv("CTRADER_NEWS_PAUSE_BEFORE_MIN", "45"))
    news_after = int(os.getenv("CTRADER_NEWS_PAUSE_AFTER_MIN", "20"))
    news_events = safety.load_news_events(os.getenv("CTRADER_NEWS_EVENTS_JSON", ""))

    if safety.abnormal_volatility(h1, max_ratio=max_atr_spike):
        return {"pair": pair, "status": "NO_TRADE", "reason_codes": ["ABNORMAL_VOLATILITY"],
                "signal_close_utc": signal_close.isoformat(), "data_source": "cTrader Open API"}
    if safety.news_blocked(signal_close, pair, news_events, pause_before_minutes=news_before, pause_after_minutes=news_after):
        return {"pair": pair, "status": "NO_TRADE", "reason_codes": ["NEWS_BLACKOUT"],
                "signal_close_utc": signal_close.isoformat(), "data_source": "cTrader Open API"}

    resolved = strategy_config(cfg)
    swing_length = resolved.pop("swing_length")
    strategy = Strategy(swing_left=swing_length, swing_right=swing_length, **resolved)
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
    base = {"pair": pair, "data_source": "cTrader Open API", "signal_close_utc": signal_close.isoformat(),
            "h1_closed": len(h1), "m5_closed": len(m5), "reason_codes": decision.reason_codes,
            "evidence": evidence, "setup_state": setup_snapshot}
    if not decision.is_signal:
        return {**base, "status": "NO_TRADE"}
    return {**base, "status": "SIGNAL_ONLY", "side": decision.side,
            "entry_price": decision.entry_price, "stop_price": decision.stop_price,
            "target_price": decision.target_price, "tp_target": decision.target_price,
            "rr": decision.risk_reward, "timestamp": signal_close.isoformat()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair", help="scan one pair instead of all configured pairs")
    args = parser.parse_args()
    cfg = load_config()
    pairs = [args.pair.upper()] if args.pair else [p.strip().upper() for p in os.getenv("CTRADER_PAIRS", ",".join(configured_pairs(cfg))).split(",") if p.strip()]
    print("=== H1/M5 BLEACH STRATEGY / cTrader ===")
    print("Order submission: DISABLED")
    for pair in pairs:
        try:
            setup_state = None
            raw_state = os.getenv("CTRADER_SETUP_STATE_JSON")
            if raw_state:
                try:
                    setup_state = json.loads(raw_state)
                except json.JSONDecodeError:
                    setup_state = None
            print(json.dumps(scan(pair, setup_state=setup_state), sort_keys=True))
        except Exception as exc:
            print(json.dumps({"pair": pair, "status": "ERROR", "error": str(exc)}))


if __name__ == "__main__":
    main()
