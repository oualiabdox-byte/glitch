#!/usr/bin/env python3
"""ICT Forex monitoring daemon using B2TRADER market data.

This process evaluates the existing ICT strategy and records signals.
Real-money order submission is deliberately disabled at the application level;
the B2TRADER execution adapter is kept separate for controlled integration.
"""

from __future__ import annotations

import json
import os
import signal
import time
from datetime import datetime, timezone, timedelta

from data.b2trader import B2TRADERGuestData
from strategy.ict_hybrid import evaluate_ict_hybrid

PAIRS = os.getenv(
    "B2TRADER_PAIRS",
    "EURUSD,GBPUSD,USDJPY,USDCHF,USDCAD,AUDUSD,NZDUSD",
).split(",")
BASE_URL = os.environ.get("B2TRADER_BASE_URL")
MARKET_PREFIX = os.getenv("B2TRADER_MARKET_PREFIX", "cfd.")
POLL_SECONDS = int(os.getenv("B2TRADER_POLL_SECONDS", "60"))
LOG_PATH = os.getenv("B2TRADER_SIGNAL_LOG", "execution/b2trader_signals.jsonl")

STOP = False


def stop(*_args):
    global STOP
    STOP = True


def market_id(pair: str) -> str:
    p = pair.strip().lower()
    return p if p.startswith("cfd.") else f"{MARKET_PREFIX}{p[:3]}_{p[3:]}"


def main():
    if not BASE_URL:
        raise SystemExit("B2TRADER_BASE_URL is required")
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    feed = B2TRADERGuestData(BASE_URL)
    print("=== ICT FOREX / B2TRADER MONITOR ===")
    print("Strategy files are unchanged.")
    print("Real-money order submission: DISABLED")

    while not STOP:
        for pair in PAIRS:
            pair = pair.strip().upper()
            if not pair:
                continue
            try:
                mid = market_id(pair)
                end = datetime.now(timezone.utc)
                # Pull a bounded recent window; the strategy consumes closed bars.
                start_h1 = end - timedelta(days=7)
                start_h4 = end - timedelta(days=30)
                h1 = feed.history_chunked(mid, "1h", start_h1, end)
                h4 = feed.history_chunked(mid, "4h", start_h4, end)
                if len(h1) < 60 or len(h4) < 30:
                    continue

                result = evaluate_ict_hybrid(h1, h4, pair)
                if result:
                    event = {
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "pair": pair,
                        "market_id": mid,
                        "side": result.get("side"),
                        "entry_zone": result.get("entry_zone"),
                        "stop_price": result.get("stop_price"),
                        "tp_target": result.get("tp_target"),
                        "rr": result.get("rr"),
                        "mode": "SIGNAL_ONLY",
                    }
                    with open(LOG_PATH, "a", encoding="utf-8") as f:
                        f.write(json.dumps(event) + "\n")
                    print(json.dumps(event))
            except Exception as exc:
                print(f"[ERROR] {pair}: {exc}")

        if not STOP:
            time.sleep(POLL_SECONDS)

    print("Stopped.")


if __name__ == "__main__":
    main()
