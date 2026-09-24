"""Export a readable Markdown research report from the local SQLite store."""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def export(database: str, output: str) -> None:
    db = sqlite3.connect(database)
    db.row_factory = sqlite3.Row
    scans = db.execute(
        "SELECT status, COUNT(*) AS n FROM scans GROUP BY status ORDER BY n DESC"
    ).fetchall()
    reasons = db.execute(
        """SELECT reason_codes_json, COUNT(*) AS n FROM scans
           WHERE reason_codes_json != '[]'
           GROUP BY reason_codes_json ORDER BY n DESC LIMIT 30"""
    ).fetchall()
    pairs = db.execute(
        "SELECT pair, COUNT(*) AS n FROM scans GROUP BY pair ORDER BY pair"
    ).fetchall()
    orders = db.execute(
        "SELECT status, COUNT(*) AS n FROM order_events GROUP BY status ORDER BY n DESC"
    ).fetchall()
    outcomes = db.execute(
        """SELECT outcome, COUNT(*) AS n, COALESCE(SUM(pnl), 0) AS pnl,
                  COALESCE(SUM(pnl_r), 0) AS pnl_r
           FROM trade_outcomes GROUP BY outcome ORDER BY outcome"""
    ).fetchall()
    lines = ["# Forex Bot Research Report", "", "## Scan totals", "", "| Status | Count |", "|---|---:|"]
    lines.extend(f"| {r['status']} | {r['n']} |" for r in scans)
    lines += ["", "## Scans by pair", "", "| Pair | Scans |", "|---|---:|"]
    lines.extend(f"| {r['pair']} | {r['n']} |" for r in pairs)
    lines += ["", "## Most common rejection codes", "", "| Reason data | Count |", "|---|---:|"]
    lines.extend(f"| `{r['reason_codes_json']}` | {r['n']} |" for r in reasons)
    lines += ["", "## Order events", "", "| Status | Count |", "|---|---:|"]
    lines.extend(f"| {r['status']} | {r['n']} |" for r in orders)
    lines += ["", "## Closed trade outcomes", "", "| Outcome | Count | PnL | PnL (R) |", "|---|---:|---:|---:|"]
    lines.extend(f"| {r['outcome'] or 'UNKNOWN'} | {r['n']} | {r['pnl']:.4f} | {r['pnl_r']:.4f} |" for r in outcomes)
    Path(output).write_text("\n".join(lines) + "\n", encoding="utf-8")
    db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default="results/trading.db")
    parser.add_argument("--output", default="results/research_report.md")
    args = parser.parse_args()
    export(args.database, args.output)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
