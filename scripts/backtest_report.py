#!/usr/bin/env python3
"""Create a Markdown backtest report and optionally retain its summary in Hindsight."""
from __future__ import annotations

import argparse
from pathlib import Path

from backtest.reporting import report_from_csv


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv")
    parser.add_argument("--output-dir", default="reports/backtests")
    parser.add_argument("--title")
    parser.add_argument("--hindsight", action="store_true")
    args = parser.parse_args()

    report, summary = report_from_csv(args.input_csv, title=args.title)
    source = Path(args.input_csv)
    output = Path(args.output_dir) / f"{source.stem}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")

    if args.hindsight:
        from intelligence.hindsight_memory import retain_event

        retain_event(
            "BACKTEST_REPORT",
            {
                "source": str(source),
                "report_path": str(output),
                "summary": summary,
            },
        )

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
