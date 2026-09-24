#!/usr/bin/env python3
"""One-shot closed-bar ICT/SMC signal scan using cTrader Open API data.

This process is signal-only. It never submits orders. Only candles whose
scheduled close time has passed are passed to the strategy.
"""
from __future__ import annotations

import json
import os
import argparse
from datetime import datetime, timezone, timedelta

from config.settings import load_config, pairs as configured_pairs
from data.ctrader import CTraderData
from strategy.decision import evaluate_entry_decision
from strategy import safety, timing


def _closed(candles, hours, now):
    """Keep only bars whose scheduled close is at or before now."""
    result = []
    for candle in candles:
        opened = datetime.fromisoformat(
            str(candle["time"]).replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        if opened + timedelta(hours=hours) <= now:
            result.append(candle)
    return result


def scan(pair: str):
    cfg = load_config()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=int(os.getenv("CTRADER_LOOKBACK_DAYS", "30")))
    feed = CTraderData()
    data = feed.download(pair, start, end, periods=("h1", "h4"))

    h1 = _closed(data["h1"], 1, end)
    h4 = _closed(data["h4"], 4, end)

    if len(h1) < 60 or len(h4) < 30:
        return {"pair": pair, "status": "NO_TRADE", "reason": "INSUFFICIENT_CLOSED_DATA",
                "h1": len(h1), "h4": len(h4)}

    latest = h1[-1]
    signal_close = datetime.fromisoformat(
        str(latest["time"]).replace("Z", "+00:00")
    ).astimezone(timezone.utc) + timedelta(hours=1)

    max_atr_spike = float(os.getenv(
        "CTRADER_MAX_ATR_SPIKE",
        cfg.get("safety", {}).get("max_atr_spike", 2.5),
    ))
    news_before = int(os.getenv("CTRADER_NEWS_PAUSE_BEFORE_MIN", "45"))
    news_after = int(os.getenv("CTRADER_NEWS_PAUSE_AFTER_MIN", "20"))
    news_events = safety.load_news_events(os.getenv("CTRADER_NEWS_EVENTS_JSON", ""))

    if safety.abnormal_volatility(h1, max_ratio=max_atr_spike):
        return {"pair": pair, "status": "NO_TRADE", "reason": "ABNORMAL_VOLATILITY",
                "signal_close_utc": signal_close.isoformat(), "data_source": "cTrader Open API"}

    if safety.news_blocked(signal_close, pair, news_events,
                            pause_before_minutes=news_before,
                            pause_after_minutes=news_after):
        return {"pair": pair, "status": "NO_TRADE", "reason": "NEWS_BLACKOUT",
                "signal_close_utc": signal_close.isoformat(), "data_source": "cTrader Open API"}

    session = timing.session_context(signal_close).session
    decision = evaluate_entry_decision(
        h1, h4, pair, "ict_fvg", session_context=session,
    )
    if not decision.is_signal:
        return {
            "pair": pair,
            "status": "NO_TRADE",
            "reason_codes": list(decision.reason_codes),
            "evidence": decision.evidence,
            "data_source": "cTrader Open API",
            "signal_close_utc": signal_close.isoformat(),
            "h1_closed": len(h1),
            "h4_closed": len(h4),
        }

    return {
        "pair": pair,
        "status": "SIGNAL_ONLY",
        "data_source": "cTrader Open API",
        "side": decision.setup["side"],
        "entry_zone": decision.setup["entry_zone"],
        "stop_price": decision.setup["stop_price"],
        "tp_target": decision.setup["tp_target"],
        "rr": decision.setup["rr"],
        "session": decision.setup["session"],
        "signal_close_utc": signal_close.isoformat(),
        "timestamp": decision.setup["timestamp"],
        "reason_codes": [],
        "evidence": decision.evidence,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pair", help="scan one pair instead of all configured pairs")
    args = parser.parse_args()
    cfg = load_config()
    pairs = [args.pair.upper()] if args.pair else [
        p.strip().upper()
        for p in os.getenv("CTRADER_PAIRS", ",".join(configured_pairs(cfg))).split(",")
        if p.strip()
    ]
    print("=== STRICT ICT/SMC FOREX / cTrader ===")
    print("Order submission: DISABLED")
    for pair in pairs:
        try:
            print(json.dumps(scan(pair)))
        except Exception as exc:
            print(json.dumps({"pair": pair, "status": "ERROR", "error": str(exc)}))


if __name__ == "__main__":
    main()
