"""Causal session and event timing context.

Internal timestamps are normalized to UTC. Session windows are interpreted in
named local time zones so daylight-saving changes do not require hard-coded UTC
offset edits. Timing is context only; it never creates a trade signal.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo


LONDON_TZ = ZoneInfo("Europe/London")
NEW_YORK_TZ = ZoneInfo("America/New_York")
LONDON_OPEN = time(8, 0)
LONDON_CLOSE = time(17, 0)
NEW_YORK_OPEN = time(8, 0)
NEW_YORK_CLOSE = time(17, 0)
LONDON_KILL_OPEN = time(8, 0)
LONDON_KILL_CLOSE = time(9, 0)
NEW_YORK_KILL_OPEN = time(8, 0)
NEW_YORK_KILL_CLOSE = time(9, 0)
OPEN_PHASE_MINUTES = 120
CLOSE_PHASE_MINUTES = 60


def as_utc(value) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise TypeError(f"unsupported timestamp type: {type(value)!r}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _minutes(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute


def _window_state(now_local: datetime, start: time, end: time):
    start_m = start.hour * 60 + start.minute
    end_m = end.hour * 60 + end.minute
    now_m = _minutes(now_local)
    return start_m <= now_m < end_m, now_m - start_m


def _phase(minutes_from_open: int | None, session_length_minutes: int = 540) -> str:
    if minutes_from_open is None:
        return "inactive"
    if minutes_from_open < OPEN_PHASE_MINUTES:
        return "open"
    if minutes_from_open >= session_length_minutes - CLOSE_PHASE_MINUTES:
        return "close"
    return "mid"


@dataclass(frozen=True)
class TimingContext:
    timestamp_utc: str
    session: str
    phase: str
    minutes_from_session_open: int | None
    london_active: bool
    new_york_active: bool
    overlap: bool


def session_context(value) -> TimingContext:
    utc = as_utc(value)
    london = utc.astimezone(LONDON_TZ)
    ny = utc.astimezone(NEW_YORK_TZ)
    london_active, london_minutes = _window_state(london, LONDON_OPEN, LONDON_CLOSE)
    ny_active, ny_minutes = _window_state(ny, NEW_YORK_OPEN, NEW_YORK_CLOSE)

    if london_active and ny_active:
        session = "overlap"
        minutes = min(london_minutes, ny_minutes)
        phase = "overlap"
    elif london_active:
        session = "london"
        minutes = london_minutes
        phase = _phase(minutes)
    elif ny_active:
        session = "new_york"
        minutes = ny_minutes
        phase = _phase(minutes)
    else:
        session = "other"
        minutes = None
        phase = "inactive"

    return TimingContext(
        timestamp_utc=utc.isoformat(),
        session=session,
        phase=phase,
        minutes_from_session_open=minutes,
        london_active=london_active,
        new_york_active=ny_active,
        overlap=london_active and ny_active,
    )


def session_at(value) -> str:
    return session_context(value).session


def phase_at(value) -> str:
    return session_context(value).phase


def in_trade_session(value) -> bool:
    return session_at(value) in {"london", "new_york", "overlap"}


def after_session_open(value, delay_minutes: int = 0) -> bool:
    ctx = session_context(value)
    if ctx.session not in {"london", "new_york", "overlap"}:
        return False
    if delay_minutes <= 0:
        return True
    return (
        ctx.minutes_from_session_open is not None
        and ctx.minutes_from_session_open >= delay_minutes
    )


def in_kill_zone(value, market=None) -> bool:
    utc = as_utc(value)
    london_local = utc.astimezone(LONDON_TZ)
    ny_local = utc.astimezone(NEW_YORK_TZ)
    london = LONDON_KILL_OPEN <= london_local.time() < LONDON_KILL_CLOSE
    new_york = NEW_YORK_KILL_OPEN <= ny_local.time() < NEW_YORK_KILL_CLOSE
    if market == "london":
        return london
    if market in {"new_york", "ny"}:
        return new_york
    return london or new_york


def current_context() -> TimingContext:
    return session_context(datetime.now(timezone.utc))
