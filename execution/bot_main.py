#!/usr/bin/env python3
"""One-shot ICT signal scan using cTrader Open API historical data.

OpenClaw can invoke this process on a schedule. Strategy logic remains
broker-independent; cTrader is the only market-data/execution boundary.
Order submission remains disabled until explicitly implemented and tested.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta

from data.ctrader import CTraderData
from strategy.ict_hybrid import evaluate_ict_hybrid

PAIRS = [
    p.strip().upper()
    for p in os.getenv(
        "CTRADER_PAIRS",
        "EURUSD,GBPUSD,USDJPY,USDCHF,USDCAD,AUDUSD,NZDUSD",
    ).split(",")
    if p.strip()
]
LOOKBACK_DAYS = int(os.getenv("CTRADER_LOOKBACK_DAYS", "30"))


def scan(pair: str):
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=LOOKBACK_DAYS)
    feed = CTraderData()
    data = feed.download(pair, start, end, periods=("h1", "h4"))
    h1, h4 = data["h1"], data["h4"]
    if len(h1) < 60 or len(h4) < 30:
        return {
            "pair": pair,
            "status": "insufficient_data",
            "h1": len(h1),
            "h4": len(h4),
        }

    setup = evaluate_ict_hybrid(h1, h4, pair)
    if not setup:
        return {
            "pair": pair,
            "status": "NO_TRADE",
            "data_source": "cTrader Open API",
            "h1": len(h1),
            "h4": len(h4),
        }

    return {
        "pair": pair,
        "status": "SIGNAL_ONLY",
        "data_source": "cTrader Open API",
        "side": setup.get("side"),
        "entry_zone": setup.get("entry_zone"),
        "stop_price": setup.get("stop_price"),
        "tp_target": setup.get("tp_target"),
        "rr": setup.get("rr"),
        "entry_model": setup.get("entry_model"),
        "entry_trigger": setup.get("entry_trigger"),
        "event_type": setup.get("event_type"),
        "confluence_score": setup.get("confluence_score"),
        "timestamp": setup.get("timestamp"),
    }


def main():
    print("=== ICT FOREX / cTrader ===")
    print("Order submission: DISABLED")
    for pair in PAIRS:
        try:
            print(json.dumps(scan(pair)))
        except Exception as exc:
            print(json.dumps({
                "pair": pair,
                "status": "ERROR",
                "error": str(exc),
            }))


if __name__ == "__main__":
    main()
