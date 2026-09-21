"""Session compatibility helpers backed by the causal timing engine."""
from .timing import (
    after_session_open,
    current_context,
    in_trade_session,
    phase_at,
    session_at,
)


def current_session():
    return current_context().session


def session_phase(value):
    return phase_at(value)


def is_london_kill_zone(value=None):
    return session_at(value or current_context().timestamp_utc) in {"london", "overlap"}


def is_ny_kill_zone(value=None):
    return session_at(value or current_context().timestamp_utc) in {"new_york", "overlap"}


def is_trade_session(value=None):
    return in_trade_session(value or current_context().timestamp_utc)


def session_open_delay_clear(value, delay_minutes=0):
    return after_session_open(value, delay_minutes)
