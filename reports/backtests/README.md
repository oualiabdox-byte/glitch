# Backtest research reports

This directory stores generated Markdown summaries of historical backtests.

Generate a report locally:

    PYTHONPATH=. python scripts/backtest_report.py path/to/results.csv --hindsight

The report is deterministic and derived from the supplied CSV. It summarizes trades, win rate, total R, average R, profit factor, pair breakdown, and strategy-variant breakdown.

Reports are research evidence only. They do not change strategy parameters, risk limits, selection, or execution.

After review, commit and push the report to the repository so Manus can read it later. Do not commit credentials, account data, API keys, or raw private market data unless that is intentionally part of the repository.
