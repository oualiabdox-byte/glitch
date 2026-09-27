#!/usr/bin/env python3
"""Small CLI for querying GLITCH's optional Hindsight research memory."""
from __future__ import annotations

import argparse

from intelligence.hindsight_memory import recall, reflect


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--reflect", action="store_true")
    args = parser.parse_args()
    result = reflect(args.query) if args.reflect else recall(args.query)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
