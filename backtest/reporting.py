"""Generate deterministic Markdown reports from backtest trade CSVs."""
from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


def _num(row: dict[str, str], *names: str) -> float | None:
    for name in names:
        value = row.get(name)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except ValueError:
            continue
    return None


def _text(row: dict[str, str], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value:
            return value
    return ""


def summarize_rows(rows: list[dict[str, str]]) -> dict[str, Any]:
    rs = []
    for row in rows:
        r = _num(row, "pnl_r", "r_multiple", "R", "r")
        if r is not None and math.isfinite(r):
            rs.append((row, r))

    wins = [r for _, r in rs if r > 0]
    losses = [r for _, r in rs if r < 0]
    total_r = sum(r for _, r in rs)
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))

    by_pair: dict[str, list[float]] = defaultdict(list)
    by_variant: dict[str, list[float]] = defaultdict(list)
    for row, r in rs:
        by_pair[_text(row, "pair", "symbol") or "UNKNOWN"].append(r)
        by_variant[_text(row, "variant", "strategy_variant") or "UNKNOWN"].append(r)

    def group(items: dict[str, list[float]]) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "trades": len(values),
                "wins": sum(v > 0 for v in values),
                "win_rate_pct": round(100 * sum(v > 0 for v in values) / len(values), 2),
                "total_r": round(sum(values), 4),
                "avg_r": round(sum(values) / len(values), 4),
            }
            for name, values in sorted(items.items())
        ]

    return {
        "trades": len(rs),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(100 * len(wins) / len(rs), 2) if rs else 0.0,
        "total_r": round(total_r, 4),
        "avg_r": round(total_r / len(rs), 4) if rs else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss else None,
        "pairs": group(by_pair),
        "variants": group(by_variant),
    }


def render_markdown(summary: dict[str, Any], *, title: str, source: str) -> str:
    pf = "∞" if summary["profit_factor"] is None and summary["trades"] else (
        f'{summary["profit_factor"]:.4f}' if summary["profit_factor"] is not None else "n/a"
    )
    lines = [
        f"# {title}",
        "",
        f"- Source: {source}",
        "- Purpose: research evidence only; no trading decision is authorized by this report.",
        "",
        "## Portfolio summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f'| Trades | {summary["trades"]} |',
        f'| Wins | {summary["wins"]} |',
        f'| Losses | {summary["losses"]} |',
        f'| Win rate | {summary["win_rate_pct"]:.2f}% |',
        f'| Total R | {summary["total_r"]:.4f} |',
        f'| Average R | {summary["avg_r"]:.4f} |',
        f"| Profit factor | {pf} |",
        "",
        "## By pair",
        "",
        "| Pair | Trades | Wins | Win rate | Total R | Avg R |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for item in summary["pairs"]:
        lines.append(
            f'| {item["name"]} | {item["trades"]} | {item["wins"]} | '
            f'{item["win_rate_pct"]:.2f}% | {item["total_r"]:.4f} | {item["avg_r"]:.4f} |'
        )

    lines += [
        "",
        "## By strategy variant",
        "",
        "| Variant | Trades | Wins | Win rate | Total R | Avg R |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for item in summary["variants"]:
        lines.append(
            f'| {item["name"]} | {item["trades"]} | {item["wins"]} | '
            f'{item["win_rate_pct"]:.2f}% | {item["total_r"]:.4f} | {item["avg_r"]:.4f} |'
        )

    lines += [
        "",
        "## Research notes",
        "",
        "- Do not treat a short sample as validation of profitability.",
        "- Compare chronological out-of-sample windows before changing strategy gates.",
        "- Preserve the source CSV and strategy/config version with this report.",
        "- Hindsight may use this report as historical evidence for later research questions.",
        "",
    ]
    return "\n".join(lines)


def report_from_csv(path: str | Path, *, title: str | None = None) -> tuple[str, dict[str, Any]]:
    source = Path(path)
    with source.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    summary = summarize_rows(rows)
    report = render_markdown(
        summary,
        title=title or f"GLITCH Backtest Report — {source.stem}",
        source=str(source),
    )
    return report, summary
