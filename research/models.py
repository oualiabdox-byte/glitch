"""Serializable research models.

These models describe observed setups and target candidates without changing
the canonical strategy behavior.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class Setup:
    setup_id: str
    pair: str
    timestamp: str
    direction: str
    d1_bias: str | None = None
    h4_context: str | None = None
    h1_structure: str | None = None
    poi_type: str | None = None
    poi_price: float | None = None
    external_sweep: bool = False
    internal_sweep: bool = False
    m5_sweep: bool = False
    bos: bool = False
    choch: bool = False
    displacement: bool = False
    entry: float | None = None
    stop: float | None = None
    current_external_target: float | None = None
    rr: float | None = None
    atr: float | None = None
    session: str | None = None
    spread: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TargetCandidate:
    setup_id: str
    candidate_id: str
    candidate_type: str
    timeframe: str
    price: float
    creation_time: str | None = None
    confirmation_time: str | None = None
    swept: bool = False
    distance_pips: float | None = None
    distance_r: float | None = None
    distance_atr: float | None = None
    target_age_hours: float | None = None
    htf_alignment: str | None = None
    opposing_liquidity: bool | None = None
    path_obstruction: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
