"""Causal MFE/MAE calculations for completed historical candles."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable


HORIZONS_MINUTES = (5, 15, 30, 60, 120, 240, 480, 1440, 2880, 4320)


@dataclass(frozen=True)
class Excursion:
    setup_id: str
    horizon_minutes: int
    mfe: float
    mae: float
    mfe_r: float | None
    mae_r: float | None
    time_to_mfe_minutes: int | None
    time_to_mae_minutes: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def calculate_excursion(
    setup_id: str,
    *,
    direction: str,
    entry: float,
    stop: float,
    entry_time: str,
    candles: Iterable[dict[str, Any]],
    horizons: tuple[int, ...] = HORIZONS_MINUTES,
) -> list[Excursion]:
    rows = sorted(candles, key=lambda c: c["time"])
    start = _dt(entry_time)
    risk = abs(entry - stop)
    results: list[Excursion] = []
    for minutes in horizons:
        end = start + timedelta(minutes=minutes)
        window = [c for c in rows if start < _dt(str(c["time"])) <= end]
        if not window:
            results.append(Excursion(setup_id, minutes, 0.0, 0.0, 0.0 if risk else None,
                                     0.0 if risk else None, None, None))
            continue
        if direction.upper() in {"LONG", "BUY"}:
            mfe = max(float(c["high"]) - entry for c in window)
            mae = max(entry - float(c["low"]) for c in window)
        else:
            mfe = max(entry - float(c["low"]) for c in window)
            mae = max(float(c["high"]) - entry for c in window)
        mfe = max(0.0, mfe)
        mae = max(0.0, mae)
        mfe_time = next(
            (_dt(str(c["time"])) for c in window
             if (float(c["high"]) - entry if direction.upper() in {"LONG", "BUY"}
                 else entry - float(c["low"])) >= mfe),
            None,
        )
        mae_time = next(
            (_dt(str(c["time"])) for c in window
             if (entry - float(c["low"]) if direction.upper() in {"LONG", "BUY"}
                 else float(c["high"]) - entry) >= mae),
            None,
        )
        results.append(Excursion(
            setup_id,
            minutes,
            mfe,
            mae,
            mfe / risk if risk else None,
            mae / risk if risk else None,
            int((mfe_time - start).total_seconds() / 60) if mfe_time else None,
            int((mae_time - start).total_seconds() / 60) if mae_time else None,
        ))
    return results
