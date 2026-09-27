from __future__ import annotations

from backtest.reporting import render_markdown, summarize_rows


def test_summary_and_report_are_deterministic():
    rows = [
        {"pair": "EURUSD", "variant": "A", "pnl_r": "1.5"},
        {"pair": "EURUSD", "variant": "A", "pnl_r": "-1"},
        {"pair": "GBPUSD", "variant": "B", "pnl_r": "0.5"},
    ]
    summary = summarize_rows(rows)
    assert summary["trades"] == 3
    assert summary["wins"] == 2
    assert summary["losses"] == 1
    assert summary["total_r"] == 1.0
    assert summary["profit_factor"] == 2.0

    report = render_markdown(summary, title="Test", source="sample.csv")
    assert "research evidence only" in report
    assert "EURUSD" in report
    assert "GBPUSD" in report


def test_missing_r_rows_are_not_counted_as_trades():
    summary = summarize_rows([
        {"pair": "EURUSD", "variant": "A", "pnl_r": ""},
        {"pair": "GBPUSD", "variant": "B", "pnl_r": "1"},
    ])
    assert summary["trades"] == 1
