#!/usr/bin/env python3
"""One-shot strict ICT/SMC signal scan using cTrader Open API data.

This process is signal-only. It never submits orders.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta

from data.ctrader import CTraderData
from strategy.ict_strategy import evaluate_ict_2022
from strategy import safety, timing

PAIRS = [
    p.strip().upper()
    for p in os.getenv(
        "CTRADER_PAIRS",
        "EURUSD,GBPUSD,USDJPY,USDCHF,USDCAD,AUDUSD,NZDUSD",
    ).split(",")
    if p.strip()
]
LOOKBACK_DAYS = int(os.getenv("CTRADER_LOOKBACK_DAYS", "30"))
MAX_ATR_SPIKE = float(os.getenv("CTRADER_MAX_ATR_SPIKE", "2.5"))
NEWS_PAUSE_BEFORE = int(os.getenv("CTRADER_NEWS_PAUSE_BEFORE_MIN", "45"))
NEWS_PAUSE_AFTER = int(os.getenv("CTRADER_NEWS_PAUSE_AFTER_MIN", "20"))
NEWS_EVENTS = safety.load_news_events(os.getenv("CTRADER_NEWS_EVENTS_JSON", ""))


def scan(pair: str):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=LOOKBACK_DAYS)
    feed = CTraderData()
    data = feed.download(pair, start, end, periods=("h1", "h4"))
    h1, h4 = data["h1"], data["h4"]

    if len(h1) < 60 or len(h4) < 30:
        return {"pair": pair, "status": "NO_TRADE", "reason": "INSUFFICIENT_DATA",
                "h1": len(h1), "h4": len(h4)}

    latest = h1[-1]
    if safety.abnormal_volatility(h1, max_ratio=MAX_ATR_SPIKE):
        return {"pair": pair, "status": "NO_TRADE", "reason": "ABNORMAL_VOLATILITY",
                "data_source": "cTrader Open API"}

    if safety.news_blocked(
        latest["time"], pair, NEWS_EVENTS,
        pause_before_minutes=NEWS_PAUSE_BEFORE,
        pause_after_minutes=NEWS_PAUSE_AFTER,
    ):
        return {"pair": pair, "status": "NO_TRADE", "reason": "NEWS_BLACKOUT",
                "data_source": "cTrader Open API"}

    session = timing.session_context(latest["time"]).session
    setup = evaluate_ict_2022(h1, h4, pair, session_context=session)
    if not setup:
        return {"pair": pair, "status": "NO_TRADE",
                "data_source": "cTrader Open API", "h1": len(h1), "h4": len(h4)}

    return {
        "pair": pair,
        "status": "SIGNAL_ONLY",
        "data_source": "cTrader Open API",
        "side": setup["side"],
        "entry_zone": setup["entry_zone"],
        "stop_price": setup["stop_price"],
        "tp_target": setup["tp_target"],
        "rr": setup["rr"],
        "session": setup["session"],
        "timestamp": setup["timestamp"],
    }


def main():
    print("=== STRICT ICT/SMC FOREX / cTrader ===")
    print("Order submission: DISABLED")
    for pair in PAIRS:
        try:
            print(json.dumps(scan(pair)))
        except Exception as exc:
            print(json.dumps({"pair": pair, "status": "ERROR", "error": str(exc)}))


if __name__ == "__main__":
    main()
