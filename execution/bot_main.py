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

from config.settings import load_config, pairs as configured_pairs
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


def scan(pair: str):
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

    strategy = Strategy(
        swing_left=int(os.getenv("CTRADER_SWING_LENGTH", "3")),
        swing_right=int(os.getenv("CTRADER_SWING_LENGTH", "3")),
        min_rr=float(os.getenv("CTRADER_MIN_RR", "0")),
        stop_buffer=float(os.getenv("CTRADER_STOP_BUFFER", "0")),
        svl_require_alignment=os.getenv("CTRADER_SVL_REQUIRE_ALIGNMENT", "false").lower() == "true",
        svl_profile_bins=int(os.getenv("CTRADER_SVL_PROFILE_BINS", "24")),
        svl_equal_tolerance_pct=float(os.getenv("CTRADER_SVL_EQUAL_TOLERANCE_PCT", "0.001")),
    )
    decision = strategy.evaluate(h1, m5)
    base = {"pair": pair, "data_source": "cTrader Open API", "signal_close_utc": signal_close.isoformat(),
            "h1_closed": len(h1), "m5_closed": len(m5), "reason_codes": decision.reason_codes,
            "evidence": decision.evidence}
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
            print(json.dumps(scan(pair), sort_keys=True))
        except Exception as exc:
            print(json.dumps({"pair": pair, "status": "ERROR", "error": str(exc)}))


if __name__ == "__main__":
    main()
