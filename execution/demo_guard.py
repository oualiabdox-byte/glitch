"""Safety gates for the optional demo execution path.

Live order routing is intentionally unsupported by this project.  This module
keeps the distinction explicit so a terminal environment cannot accidentally
turn a demo runner into a live trader.
"""
from __future__ import annotations

import os


DEMO_CONFIRMATION = "I_UNDERSTAND_DEMO_TRADING"


def require_demo_execution() -> None:
    """Require explicit, demo-only authorization before any order request.

    Credentials may be loaded from the shell or a local, ignored ``.env``.
    This gate does not validate the strategy or guarantee profitability; it
    only prevents accidental live routing and missing volume limits.
    """
    environment = os.getenv("CTRADER_ENV", "demo").strip().lower()
    if environment != "demo":
        raise RuntimeError(
            "Demo execution only: CTRADER_ENV must be exactly 'demo'. "
            "Live order routing is not implemented."
        )
    if os.getenv("CTRADER_ALLOW_ORDERS", "false").strip().lower() != "true":
        raise RuntimeError(
            "Demo orders are disabled. Set CTRADER_ALLOW_ORDERS=true only "
            "for an intentional cTrader demo run."
        )
    if os.getenv("CTRADER_DEMO_CONFIRM", "") != DEMO_CONFIRMATION:
        raise RuntimeError(
            "Demo orders require CTRADER_DEMO_CONFIRM="
            f"{DEMO_CONFIRMATION}"
        )
    try:
        cap = float(os.getenv("CTRADER_MAX_ORDER_VOLUME_UNITS", "0"))
    except ValueError as exc:
        raise RuntimeError("CTRADER_MAX_ORDER_VOLUME_UNITS must be numeric") from exc
    if cap <= 0:
        raise RuntimeError(
            "Demo orders require CTRADER_MAX_ORDER_VOLUME_UNITS > 0; "
            "never run without an explicit volume cap."
        )


def live_execution_is_disabled() -> bool:
    """Return True because this repository intentionally has no live path."""
    return True
