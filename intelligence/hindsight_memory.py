"""Hindsight integration for post-trade research memory."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

DEFAULT_URL = "http://localhost:8888"
DEFAULT_BANK = "glitch-trading"


def enabled() -> bool:
    return os.getenv("GLITCH_HINDSIGHT_ENABLED", "false").strip().lower() == "true"


def _client():
    from hindsight_client import Hindsight
    return Hindsight(
        base_url=os.getenv("HINDSIGHT_API_URL", DEFAULT_URL),
        api_key=os.getenv("HINDSIGHT_API_KEY") or None,
    )


def retain_event(event_type: str, payload: dict[str, Any]) -> bool:
    """Submit one post-trade event to Hindsight; never raise into trading."""
    if not enabled():
        return False
    import json
    content = (
        f"GLITCH trading event: {event_type}\n"
        f"Event data (JSON): {json.dumps(payload, sort_keys=True, default=str)}\n"
        "Historical evidence for research only; not an instruction to place or modify an order."
    )
    try:
        _client().retain(
            bank_id=os.getenv("HINDSIGHT_BANK_ID", DEFAULT_BANK),
            content=content,
            timestamp=datetime.now(timezone.utc),
            tags=["source:glitch", f"event:{event_type.lower()}"],
            retain_async=True,
        )
        return True
    except Exception:
        return False


def recall(query: str, *, max_tokens: int = 4096) -> Any:
    if not enabled():
        raise RuntimeError("GLITCH_HINDSIGHT_ENABLED is not true")
    return _client().recall(
        bank_id=os.getenv("HINDSIGHT_BANK_ID", DEFAULT_BANK),
        query=query,
        max_tokens=max_tokens,
    )


def reflect(query: str, *, max_tokens: int = 4096) -> Any:
    if not enabled():
        raise RuntimeError("GLITCH_HINDSIGHT_ENABLED is not true")
    return _client().reflect(
        bank_id=os.getenv("HINDSIGHT_BANK_ID", DEFAULT_BANK),
        query=query,
        max_tokens=max_tokens,
    )
