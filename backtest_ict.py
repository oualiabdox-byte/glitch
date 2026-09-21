#!/usr/bin/env python3
"""Compatibility entry point for the cTrader-backed ICT backtest.

The old MT5/Kraken skeleton has been removed from this entry point.
Use cTrader Open API for historical OHLC and the existing strategy modules
for signal generation and trade simulation.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone, timedelta

from backtest.ctrader_runner import run


def main():
    p = argparse.ArgumentParser()
    p.add_argument("pair", nargs="?", default="EURUSD")
    p.add_argument("--days", type=int, default=120)
    p.add_argument("--start")
    p.add_argument("--end")
    args = p.parse_args()

    end = (
        datetime.fromisoformat(args.end.replace("Z", "+00:00")).astimezone(timezone.utc)
        if args.end
        else datetime.now(timezone.utc)
    )
    start = (
        datetime.fromisoformat(args.start.replace("Z", "+00:00")).astimezone(timezone.utc)
        if args.start
        else end - timedelta(days=args.days)
    )
    print(json.dumps(run(args.pair, start, end), indent=2))


if __name__ == "__main__":
    main()
