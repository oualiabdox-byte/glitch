#!/usr/bin/env python3
"""Download cTrader M5 data with native volume, without storing credentials.

Credentials must be injected by the caller through environment variables:
CTRADER_CLIENT_ID, CTRADER_CLIENT_SECRET, CTRADER_ACCESS_TOKEN.
CTRADER_REFRESH_TOKEN is accepted by the surrounding environment but is not
written or refreshed by this script. Alternatively, copy
config/ctrader_credentials.env.example to config/ctrader_credentials.env and
fill it locally; that file is ignored by Git. Order execution is always disabled.

Example (keys are not saved):
  CTRADER_CLIENT_ID='...' CTRADER_CLIENT_SECRET='...' \
  CTRADER_ACCESS_TOKEN='...' CTRADER_ENV=demo \
  PYTHONPATH=. .venv/bin/python backtest/fetch_ctrader_volume_dataset.py \
    --days 10 --pairs EURUSD,GBPUSD
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

from data.ctrader import CTraderData


DEFAULT_PAIRS = "EURUSD,GBPUSD,USDJPY,USDCHF,USDCAD,AUDUSD,NZDUSD"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=10)
    parser.add_argument("--pairs", default=os.getenv("CTRADER_PAIRS", DEFAULT_PAIRS))
    parser.add_argument("--period", choices=("m5", "m15", "h1"), default="m5")
    parser.add_argument("--output-dir", type=Path, default=Path("backtest/ctrader_volume_data"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/ctrader_cache"))
    parser.add_argument("--credentials-file", type=Path, default=Path("config/ctrader_credentials.env"))
    return parser.parse_args()


def require_safe_environment() -> None:
    if os.getenv("CTRADER_ENV", "demo").strip().lower() != "demo":
        raise RuntimeError("Refusing download unless CTRADER_ENV=demo")
    if os.getenv("CTRADER_ALLOW_ORDERS", "false").strip().lower() == "true":
        raise RuntimeError("Refusing download while CTRADER_ALLOW_ORDERS=true")
    if os.getenv("CTRADER_DEMO_EXECUTE", "false").strip().lower() == "true":
        raise RuntimeError("Refusing download while CTRADER_DEMO_EXECUTE=true")
    for name in ("CTRADER_CLIENT_ID", "CTRADER_CLIENT_SECRET", "CTRADER_ACCESS_TOKEN"):
        if not os.getenv(name, "").strip():
            raise RuntimeError(f"{name} is required in the current process environment")


def main() -> int:
    args = parse_args()
    if args.days <= 0:
        raise ValueError("--days must be positive")
    if args.credentials_file.exists():
        load_dotenv(args.credentials_file, override=False)
    require_safe_environment()

    end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = end - timedelta(days=args.days)
    pairs = [p.strip().upper() for p in args.pairs.split(",") if p.strip()]
    if not pairs:
        raise ValueError("No pairs supplied")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    provider = CTraderData(cache_dir=str(args.cache_dir))
    summary: list[dict] = []
    for pair in pairs:
        print(f"Downloading {pair} {args.period}: {start.isoformat()} -> {end.isoformat()}", flush=True)
        result = provider.download(pair, start, end, periods=(args.period,), use_cache=False)
        rows = result[args.period]
        destination = args.output_dir / f"{pair}_{args.period}_{args.days}d.json"
        destination.write_text(json.dumps({"pair": pair, "period": args.period, "start": start.isoformat(), "end": end.isoformat(), "candles": rows}, indent=2) + "\n")
        positive = sum(1 for row in rows if isinstance(row.get("volume"), (int, float)) and row.get("volume", 0) > 0)
        summary.append({"pair": pair, "candles": len(rows), "positive_volume": positive, "file": str(destination)})
        print(json.dumps(summary[-1], sort_keys=True), flush=True)

    print(json.dumps({"start": start.isoformat(), "end": end.isoformat(), "results": summary}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
