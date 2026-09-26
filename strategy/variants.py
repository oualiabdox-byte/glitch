"""Named, reproducible strategy presets used by the variant backtests.

These presets wrap the existing forex_bot Strategy without changing its signal
logic. They only select the causal swing length and M5 confirmation mode.
"""
from __future__ import annotations

from collections.abc import Mapping

from .engine import Strategy

VARIANTS = {
    "eurusd_swing3_choch_or_bos": {
        "pair": "EURUSD",
        "swing_length": 3,
        "m5_confirmation_mode": "CHOCH_OR_BOS",
    },
    "gbpusd_swing2_choch_only": {
        "pair": "GBPUSD",
        "swing_length": 2,
        "m5_confirmation_mode": "CHOCH_ONLY",
    },
    "eurusd_swing2_choch_or_bos": {
        "pair": "EURUSD",
        "swing_length": 2,
        "m5_confirmation_mode": "CHOCH_OR_BOS",
    },
}


def available_variants() -> tuple[str, ...]:
    return tuple(VARIANTS)


def variants_for_pair(pair: str) -> tuple[str, ...]:
    """Return every registered preset for a pair, preserving registration order."""
    normalized = "".join(character for character in str(pair).upper() if character.isalpha())
    return tuple(name for name, spec in VARIANTS.items() if spec["pair"] == normalized)


def build_variant(name: str, base_options: Mapping[str, object] | None = None) -> Strategy:
    """Build one named preset, optionally retaining non-preset runtime options."""
    try:
        spec = VARIANTS[name]
    except KeyError as exc:
        raise ValueError(f"unknown strategy variant: {name!r}; choose from {available_variants()}") from exc
    swing = int(spec["swing_length"])
    options = dict(base_options or {})
    options.pop("swing_length", None)
    options["m5_confirmation_mode"] = str(spec["m5_confirmation_mode"])
    return Strategy(
        swing_left=swing,
        swing_right=swing,
        **options,
    )
