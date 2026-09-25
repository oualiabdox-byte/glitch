"""Deterministic data-quality checks for the cTrader H1/M5 strategy."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone


def _utc(value):
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def validate_ohlc(bars, interval_minutes, name="bars"):
    errors, warnings = [], []
    if not bars:
        return {"valid": False, "errors": [f"{name}:EMPTY"], "warnings": []}
    previous, seen = None, set()
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


def validate_h1_m5_alignment(h1, m5):
    errors = []
    for series, interval, name in ((h1, 60, "h1"), (m5, 5, "m5")):
        for previous, current in zip(series, series[1:]):
            delta = _utc(current["time"]) - _utc(previous["time"])
            if delta <= timedelta(minutes=interval) or delta > timedelta(minutes=interval * 2):
                continue
            errors.append(f"{name}:INVALID_INTERVAL:{_utc(current['time']).isoformat()}")
    return {"valid": not errors, "errors": errors, "warnings": [], "h1_bars": len(h1), "m5_bars": len(m5)}


def validate_dataset(h1, m5):
    h1_report = validate_ohlc(h1, 60, "h1")
    m5_report = validate_ohlc(m5, 5, "m5")
    alignment = validate_h1_m5_alignment(h1, m5)
    errors = h1_report["errors"] + m5_report["errors"] + alignment["errors"]
    warnings = h1_report["warnings"] + m5_report["warnings"]
    return {"valid": not errors, "errors": errors, "warnings": warnings,
            "h1": h1_report, "m5": m5_report, "alignment": alignment}
