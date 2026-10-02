"""CRT/TBS trader adapter for research backtests.

This adapter turns the repository's existing M5 cTrader data into a CRT/TBS
signal stream. It is deliberately separate from the live canonical SMC engine
until walk-forward validation and the broken engine loader are repaired.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from backtest.crt_tbs_14d import body_tbs_candidates, complete_bars, htf_purges, simulate_trade


@dataclass(frozen=True)
class CrtTbsTrader:
    htf_rule: str = "2h"
    entry_rule: str = "body_close_reentry"
    min_structure_gap: int = 2
    max_structure_gap: int = 6

    def signals(self, frame: pd.DataFrame, instrument: str, symbol: str = "") -> list[dict[str, Any]]:
        """Generate one causal trade record per completed CRT purge window."""
        m5, htf = complete_bars(frame)
        trades = []
        for bucket, purge in htf_purges(m5, htf).items():
            bucket_position = htf.index.get_loc(bucket)
            if bucket_position + 1 >= len(htf):
                continue
            next_bucket = htf.index[bucket_position + 1]
            start = int(m5.index.searchsorted(bucket))
            end = int(m5.index.searchsorted(next_bucket))
            if end <= start + 8:
                continue
            candidates = body_tbs_candidates(m5, start, end, purge["side"])
            if not candidates:
                continue
            trade = simulate_trade(m5, candidates[0], purge["side"], purge, purge["purge_time"])
            if trade is None:
                continue
            trade.instrument, trade.symbol = instrument, symbol
            trades.append(trade)
        return [trade.__dict__.copy() for trade in trades]

    def report(self) -> dict[str, str]:
        return {
            "htf_rule": self.htf_rule,
            "entry_rule": self.entry_rule,
            "structure_gap": f"{self.min_structure_gap}-{self.max_structure_gap} M5 candles",
            "execution": "research_only_no_orders",
        }
