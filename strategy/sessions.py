"""Session detection: London / NY / overlap timing (UTC-based)."""
import datetime


def current_session():
    """Determine which ICT session is currently active based on UTC time."""
    now = datetime.datetime.utcnow()
    hour = now.hour
    # London session: 07:00 - 12:00 UTC
    # NY session: 13:00 - 17:00 UTC (13:30 NY open, but using 13 for simplicity)
    # Overlap: 12:00 - 13:00 UTC (London close / NY open)
    if 7 <= hour < 12:
        return "london"
    if 13 <= hour < 17:
        return "new_york"
    if 12 <= hour < 13:
        return "overlap"
    # Asian session (before London open)
    if 0 <= hour < 7:
        return "asian"
    # After NY close
    return "other"


def is_london_kill_zone():
    s = current_session()
    return s in ("london", "overlap")


def is_ny_kill_zone():
    s = current_session()
    return s in ("new_york",)
