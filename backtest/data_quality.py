"""Deterministic data-quality checks for historical OHLC backtests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _utc(value):
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def validate_ohlc(bars, interval_minutes, name="bars"):
    """Return errors/warnings without silently repairing source data."""
    errors, warnings = [], []
    if not bars:
        return {"valid": False, "errors": [f"{name}:EMPTY"], "warnings": []}
    previous = None
    seen = set()
    expected = timedelta(minutes=interval_minutes)
    for index, bar in enumerate(bars):
        try:
            timestamp = _utc(bar["time"])
            values = {key: float(bar[key]) for key in ("open", "high", "low", "close")}
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"{name}:ROW_{index}_INVALID:{exc}")
            continue
        if timestamp in seen:
            errors.append(f"{name}:DUPLICATE_TIME:{timestamp.isoformat()}")
        seen.add(timestamp)
        if previous is not None:
            if timestamp <= previous:
                errors.append(f"{name}:NON_MONOTONIC:{timestamp.isoformat()}")
            elif timestamp - previous > expected * 2:
                warnings.append(f"{name}:GAP:{previous.isoformat()}->{timestamp.isoformat()}")
        previous = timestamp
        if values["high"] < max(values["open"], values["close"]) or values["low"] > min(values["open"], values["close"]):
            errors.append(f"{name}:OHLC_INCONSISTENT:{timestamp.isoformat()}")
        if values["high"] < values["low"]:
            errors.append(f"{name}:HIGH_BELOW_LOW:{timestamp.isoformat()}")
        if any(value != value for value in values.values()):
            errors.append(f"{name}:NAN:{timestamp.isoformat()}")
    return {"valid": not errors, "errors": errors, "warnings": warnings, "bars": len(bars)}


def validate_h1_h4_alignment(h1, h4):
    """Check a stable broker bar axis, without assuming UTC hour zero."""
    errors = []
    if h4:
        first = _utc(h4[0]["time"])
        axis = (first.minute, first.second, first.microsecond, first.hour % 4)
        for bar in h4:
            timestamp = _utc(bar["time"])
            if (timestamp.minute, timestamp.second, timestamp.microsecond, timestamp.hour % 4) != axis:
                errors.append(f"h4:UNSTABLE_AXIS:{timestamp.isoformat()}")
    for previous, current in zip(h4, h4[1:]):
        delta = _utc(current["time"]) - _utc(previous["time"])
        if delta > timedelta(hours=4):
            continue  # Weekend/market-closed gap; retain it as a warning upstream.
        if delta != timedelta(hours=4):
            errors.append(f"h4:INVALID_INTERVAL:{_utc(current['time']).isoformat()}")
    return {"valid": not errors, "errors": errors, "warnings": [], "h1_bars": len(h1), "h4_bars": len(h4)}


def validate_dataset(h1, h4):
    h1_report = validate_ohlc(h1, 60, "h1")
    h4_report = validate_ohlc(h4, 240, "h4")
    alignment = validate_h1_h4_alignment(h1, h4)
    errors = h1_report["errors"] + h4_report["errors"] + alignment["errors"]
    warnings = h1_report["warnings"] + h4_report["warnings"]
    return {"valid": not errors, "errors": errors, "warnings": warnings,
            "h1": h1_report, "h4": h4_report, "alignment": alignment}
