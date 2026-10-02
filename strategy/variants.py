"""Named pair-routing presets for the installed CRT M15/4H engine."""
from __future__ import annotations

from collections.abc import Mapping

from .crt_trader import CrtM15Strategy

CONFIG_DEFAULT = "config_default"

# Priority is deliberately tied: the short earlier experiment is not a reliable
# basis for favoring one preset. RR, existing structure strength, and stable
# deterministic tie-breaks select among same-direction signals instead.
VARIANTS = {
    "eurusd_swing3_choch_or_bos": {
        "pair": "EURUSD", "swing_length": 3,
        "m5_confirmation_mode": "BOS_AFTER_CHOCH", "priority": 100,
    },
    "gbpusd_swing2_choch_only": {
        "pair": "GBPUSD", "swing_length": 2,
        "m5_confirmation_mode": "CHOCH_ONLY", "priority": 100,
    },
    "eurusd_swing2_choch_or_bos": {
        "pair": "EURUSD", "swing_length": 2,
        "m5_confirmation_mode": "BOS_AFTER_CHOCH", "priority": 100,
    },
}


def available_variants() -> tuple[str, ...]:
    return tuple(VARIANTS)


def variants_for_pair(pair: str) -> tuple[str, ...]:
    """Return every registered preset for a pair, preserving registry order."""
    normalized = "".join(character for character in str(pair).upper() if character.isalpha())
    return tuple(name for name, spec in VARIANTS.items() if spec["pair"] == normalized)


def build_variant(name: str, base_options: Mapping[str, object] | None = None) -> CrtM15Strategy:
    """Build the selected CRT M15/4H production engine.

    The historical SMC variant registry is retained for pair routing and
    compatibility, but all variants now share the one tested CRT engine.
    """
    if name != CONFIG_DEFAULT and name not in VARIANTS:
        raise ValueError(f"unknown strategy variant: {name!r}; choose from {available_variants()}")
    return CrtM15Strategy()
