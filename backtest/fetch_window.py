"""Fetch one cTrader period in a fresh process so Twisted reactor is reusable."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from data.ctrader import CTraderData


parser = argparse.ArgumentParser()
parser.add_argument("--symbol", required=True)
parser.add_argument("--period", choices=("d1", "h1", "m5"), required=True)
parser.add_argument("--start", required=True)
parser.add_argument("--end", required=True)
parser.add_argument("--cache-dir", required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()

feed = CTraderData(cache_dir=args.cache_dir)
rows = feed.download(args.symbol, args.start, args.end, periods=(args.period,))
Path(args.output).write_text(json.dumps(rows, indent=2))
print(f"fetched {args.period}: {len(rows.get(args.period, []))}")
