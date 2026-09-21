"""Single source of truth for runtime configuration.

YAML is loaded once by callers; environment variables may override credentials
and explicitly operational switches, but strategy/backtest defaults live here.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

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


def risk_config(config: dict[str, Any]) -> dict[str, Any]:
    return dict(config.get("risk", {}))


def execution_config(config: dict[str, Any]) -> dict[str, Any]:
    return dict(config.get("execution", {}))
