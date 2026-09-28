"""Single source of truth for runtime configuration.

YAML owns strategy defaults; explicitly named environment variables override
those defaults. Credentials and operational controls remain environment-based.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "config" / "config.yaml"


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    p = Path(path)
    data = yaml.safe_load(p.read_text()) or {}
    if not isinstance(data, dict):
        raise ValueError("config.yaml root must be a mapping")
    return data


def pairs(config: dict[str, Any]) -> list[str]:
    values = config.get("pairs", [])
    if not isinstance(values, list) or not all(isinstance(x, str) for x in values):
        raise ValueError("config.pairs must be a list of strings")
    return [x.strip().upper() for x in values if x.strip()]


def risk_config(config: dict[str, Any], environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Resolve risk settings from YAML, with explicit environment overrides."""
    env = os.environ if environ is None else environ
    risk = dict(config.get("risk", {}))
    risk["max_quote_age_seconds"] = _env_value(
        env, "CTRADER_MAX_QUOTE_AGE_SECONDS", risk.get("max_quote_age_seconds", 60), int)
    if risk["max_quote_age_seconds"] < 1:
        raise ValueError("max_quote_age_seconds must be >= 1")
    return risk


def execution_config(config: dict[str, Any]) -> dict[str, Any]:
    return dict(config.get("execution", {}))


def _env_value(environ: Mapping[str, str], key: str, default: Any, convert):
    if key not in environ:
        return default
    try:
        return convert(environ[key])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} has invalid value {environ[key]!r}") from exc


def _env_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise ValueError("expected true/false")


def strategy_config(config: dict[str, Any], environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Return the resolved strategy parameters, with explicit env overrides."""
    env = os.environ if environ is None else environ
    strategy = dict(config.get("strategy", {}))
    svl = dict(strategy.get("svl", {}))
    resolved = {
        "swing_length": _env_value(env, "CTRADER_SWING_LENGTH", strategy.get("swing_length", 2), int),
        "min_rr": _env_value(env, "CTRADER_MIN_RR", strategy.get("min_rr", 0.0), float),
        "stop_buffer": _env_value(env, "CTRADER_STOP_BUFFER", strategy.get("stop_buffer", 0.0), float),
        "allow_weak_structure": _env_value(env, "CTRADER_ALLOW_WEAK_STRUCTURE",
                                            strategy.get("allow_weak_structure", True), _env_bool),
        "allow_equilibrium_overlapping_fvg": _env_value(
            env, "CTRADER_ALLOW_EQUILIBRIUM_OVERLAPPING_FVG",
            strategy.get("allow_equilibrium_overlapping_fvg", True), _env_bool),
        "setup_max_age_hours": _env_value(
            env, "CTRADER_SETUP_MAX_AGE_HOURS", strategy.get("setup_max_age_hours", 72), int),
        "m5_confirmation_mode": _env_value(
            env, "CTRADER_M5_CONFIRMATION_MODE", strategy.get("m5_confirmation_mode", "CHOCH_OR_BOS"), str),
        "svl_require_alignment": _env_value(env, "CTRADER_SVL_REQUIRE_ALIGNMENT",
                                             svl.get("require_alignment", False), _env_bool),
        "svl_profile_bins": _env_value(env, "CTRADER_SVL_PROFILE_BINS", svl.get("profile_bins", 24), int),
        "svl_equal_tolerance_pct": _env_value(
            env, "CTRADER_SVL_EQUAL_TOLERANCE_PCT", svl.get("equal_tolerance_pct", 0.001), float),
    }
    optional = (("require_killzone", "CTRADER_REQUIRE_KILLZONE", _env_bool, False),
                ("require_displacement", "CTRADER_REQUIRE_DISPLACEMENT", _env_bool, False),
                ("min_displacement_ratio", "CTRADER_MIN_DISPLACEMENT_RATIO", float, 1.0),
                ("require_poi_confluence", "CTRADER_REQUIRE_POI_CONFLUENCE", _env_bool, False))
    for key, env_key, converter, default in optional:
        if env_key in env or key in strategy:
            resolved[key] = _env_value(env, env_key, strategy.get(key, default), converter)
    return resolved
