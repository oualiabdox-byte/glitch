"""Named, reproducible configurations of the canonical forex_bot Strategy."""
from __future__ import annotations

from collections.abc import Mapping

from .engine import Strategy

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


def build_variant(name: str, base_options: Mapping[str, object] | None = None) -> Strategy:
    """Build the canonical Strategy with a named preset or configured default.

    Named variants override only their swing length and use the strict SMC
    confirmation mode; all risk and confluence gates flow from runtime config.
    """
    if base_options is None:
        # Keep every caller on the same strict SMC contract as live scanning.
        from config.settings import load_config, strategy_config
        options = strategy_config(load_config())
    else:
        options = dict(base_options)
    if name == CONFIG_DEFAULT:
        swing = int(options.pop("swing_length", 3))
        mode = str(options.pop("m5_confirmation_mode", "CHOCH_OR_BOS"))
    else:
        try:
            spec = VARIANTS[name]
        except KeyError as exc:
            raise ValueError(
                f"unknown strategy variant: {name!r}; choose from {available_variants()}"
            ) from exc
        swing = int(spec["swing_length"])
        mode = str(spec["m5_confirmation_mode"])
        options.pop("swing_length", None)
    options["m5_confirmation_mode"] = mode
    return Strategy(swing_left=swing, swing_right=swing, **options)
