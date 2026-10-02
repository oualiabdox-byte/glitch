"""Production-facing CRT M15/4H execution strategy.

The selected research configuration is intentionally narrow:
- 2H CRT range and purge
- M15 execution candles
- 4H post-purge search window
- equal-level gap 2–6 M15 candles
- entry body ratio >= 0.30
- no minimum stop-distance filter

The strategy emits a closed-bar Decision only. It never submits orders.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pandas as pd

from backtest.crt_tbs_14d import body_tbs_candidates, htf_purges, simulate_trade
from strategy.models import Decision


@dataclass(frozen=True)
class CrtM15Strategy:
    htf_rule: str = "2h"
    execution_timeframe: str = "15m"
    post_purge_window_hours: int = 4
    min_structure_gap: int = 2
    max_structure_gap: int = 6
    min_entry_body_ratio: float = 0.30
    min_stop_distance_atr: float = 0.0

    @staticmethod
    def _frame(rows: Any) -> pd.DataFrame:
        if isinstance(rows, pd.DataFrame):
            frame = rows.copy()
        else:
            frame = pd.DataFrame(list(rows or []))
        if frame.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"],
                                index=pd.DatetimeIndex([], tz="UTC"))
        if "time" in frame.columns:
            frame["time"] = pd.to_datetime(frame["time"], utc=True)
            frame = frame.set_index("time")
        elif not isinstance(frame.index, pd.DatetimeIndex):
            frame.index = pd.to_datetime(frame.index, utc=True)
        frame = frame.sort_index().loc[~frame.index.duplicated(keep="last")]
        required = ["open", "high", "low", "close"]
        if not all(column in frame.columns for column in required):
            return pd.DataFrame(columns=required + ["volume"], index=pd.DatetimeIndex([], tz="UTC"))
        if "volume" not in frame.columns:
            frame["volume"] = 0.0
        return frame[required + ["volume"]].astype(float)

    @staticmethod
    def _aggregate_m15(m5: pd.DataFrame) -> pd.DataFrame:
        if m5.empty:
            return m5
        return m5.resample("15min", label="left", closed="left").agg({
            "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
        }).dropna()

    @staticmethod
    def _complete_2h(m15: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        if m15.empty:
            return m15, m15.copy()
        counts = m15["close"].resample("2h", label="left", closed="left").count()
        htf = m15.resample("2h", label="left", closed="left").agg({
            "open": "first", "high": "max", "low": "min", "close": "last"
        }).dropna()
        valid = counts[counts >= 8].index
        return m15, htf.loc[htf.index.intersection(valid)]

    def _trades(self, m5_rows: Any, *, active_only: bool = False) -> list[dict[str, Any]]:
        m5 = self._frame(m5_rows)
        m15 = self._aggregate_m15(m5)
        if len(m15) < 12:
            return []
        m15, htf = self._complete_2h(m15)
        purges = htf_purges(m15, htf)
        result: list[dict[str, Any]] = []
        latest_time = m15.index[-1]
        latest_index = len(m15) - 1
        for bucket, purge in purges.items():
            position = htf.index.get_loc(bucket)
            if position + 2 >= len(htf):
                continue
            start = int(m15.index.searchsorted(bucket))
            window_end = htf.index[position + 2]
            if active_only:
                if latest_time < bucket or latest_time >= window_end:
                    continue
                end = min(latest_index + 1, int(m15.index.searchsorted(window_end)))
            else:
                end = int(m15.index.searchsorted(window_end))
            if end <= start + 8:
                continue
            candidates = body_tbs_candidates(
                m15, start, end, purge["side"],
                min_gap=self.min_structure_gap,
                max_gap=self.max_structure_gap,
            )
            for candidate in (candidates[-1:] if active_only else candidates[:1]):
                trade = simulate_trade(m15, candidate, purge["side"], purge, purge["purge_time"])
                if trade is None:
                    continue
                if trade.entry_body_ratio < self.min_entry_body_ratio:
                    continue
                if self.min_stop_distance_atr > 0 and trade.stop_distance_atr < self.min_stop_distance_atr:
                    continue
                trade.instrument = ""
                trade.symbol = ""
                result.append(trade.__dict__.copy())
        return result

    def signals(
        self,
        frame: pd.DataFrame,
        instrument: str,
        symbol: str = "",
        diagnostics: dict[str, int] | None = None,
    ) -> list[dict[str, Any]]:
        trades = self._trades(frame, active_only=False)
        for trade in trades:
            trade["instrument"] = instrument
            trade["symbol"] = symbol or instrument
        if diagnostics is not None:
            diagnostics.update({"execution_timeframe": "15m", "post_purge_window_hours": 4,
                                "min_entry_body_ratio": self.min_entry_body_ratio,
                                "min_stop_distance_atr": self.min_stop_distance_atr,
                                "trades_accepted": len(trades)})
        return trades

    def evaluate(self, h1_rows, m5_rows, setup_state=None, h4_rows=None, d1_rows=None) -> Decision:
        trades = self._trades(m5_rows, active_only=True)
        if not trades:
            return Decision(status="NO_TRADE", reason_codes=["NO_ACTIVE_CRT_M15_SETUP"], evidence=self.report())
        trade = trades[-1]
        entry_time = str(trade["entry_time"])
        previous = (setup_state or {}).get("last_entry_time") if isinstance(setup_state, dict) else None
        if previous and str(previous) == entry_time:
            return Decision(status="NO_TRADE", reason_codes=["DUPLICATE_CRT_SETUP"], evidence={"entry_time": entry_time, **self.report()})
        entry = float(trade["entry"]); stop = float(trade["stop"]); target = float(trade["target"])
        risk = abs(entry - stop)
        rr = abs(target - entry) / risk if risk > 0 else 0.0
        side = "LONG" if trade["side"] == "LONG" else "SHORT"
        evidence = {**self.report(), "entry_time": entry_time, "htf_purge_time": trade["htf_purge_time"],
                    "liquidity_level": trade["liquidity_level"], "entry_body_ratio": trade["entry_body_ratio"],
                    "stop_distance_atr": trade["stop_distance_atr"], "target_distance_atr": trade["target_distance_atr"],
                    "session": trade["session"], "volatility_regime": trade["volatility_regime"]}
        return Decision(status="SIGNAL", reason_codes=["CRT_M15_4H", "BODY_RATIO_0_30"],
                        side=side, entry_price=entry, stop_price=stop, target_price=target,
                        risk_reward=rr, evidence=evidence)

    def report(self) -> dict[str, Any]:
        return {"engine": "CRT_M15_4H_BODY_030", "htf_rule": self.htf_rule,
                "execution_timeframe": self.execution_timeframe,
                "post_purge_window_hours": self.post_purge_window_hours,
                "structure_gap": f"{self.min_structure_gap}-{self.max_structure_gap} M15 candles",
                "min_entry_body_ratio": self.min_entry_body_ratio,
                "min_stop_distance_atr": self.min_stop_distance_atr,
                "execution": "production_signal_interface_no_order_submission"}


# Backward-compatible name for research callers.
CrtTbsTrader = CrtM15Strategy
