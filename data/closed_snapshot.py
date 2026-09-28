"""Authoritative causal closed-bar snapshot boundary."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable


TIMEFRAME_MINUTES = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
}


def candle_is_closed(candle: dict[str, Any], timeframe: str, as_of: datetime) -> bool:
    tf = str(timeframe).upper()
    if tf not in TIMEFRAME_MINUTES:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    opened = datetime.fromisoformat(str(candle["time"]).replace("Z", "+00:00"))
    if opened.tzinfo is None:
        opened = opened.replace(tzinfo=timezone.utc)
    opened = opened.astimezone(timezone.utc)
    as_of = as_of.astimezone(timezone.utc)
    return opened + timedelta(minutes=TIMEFRAME_MINUTES[tf]) <= as_of


def closed_candles(
    candles: Iterable[dict[str, Any]],
    timeframe: str,
    as_of: datetime,
) -> tuple[dict[str, Any], ...]:
    rows = [c for c in candles if candle_is_closed(c, timeframe, as_of)]
    return tuple(sorted(rows, key=lambda c: c["time"]))


@dataclass(frozen=True)
class ClosedBarSnapshot:
    as_of: datetime
    frames: dict[str, tuple[dict[str, Any], ...]]

    @classmethod
    def build(
        cls,
        *,
        as_of: datetime,
        candles_by_timeframe: dict[str, Iterable[dict[str, Any]]],
    ) -> "ClosedBarSnapshot":
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        normalized = {
            timeframe.upper(): closed_candles(candles, timeframe, as_of)
            for timeframe, candles in candles_by_timeframe.items()
        }
        return cls(as_of=as_of.astimezone(timezone.utc), frames=normalized)

    def candles(self, timeframe: str) -> tuple[dict[str, Any], ...]:
        return self.frames.get(str(timeframe).upper(), ())
