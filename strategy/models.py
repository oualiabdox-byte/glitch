from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Side = Literal["LONG", "SHORT"]


@dataclass(frozen=True)
class Candle:
    time: str
    open: float
    high: float
    low: float
    close: float

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "Candle":
        return cls(str(row["time"]), float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]))


@dataclass(frozen=True)
class Swing:
    index: int
    kind: Literal["HIGH", "LOW"]
    price: float
    time: str


@dataclass(frozen=True)
class FairValueGap:
    index: int
    side: Side
    bottom: float
    top: float
    time: str

    def contains(self, price: float) -> bool:
        return self.bottom <= price <= self.top

    def overlaps(self, candle: Candle) -> bool:
        return candle.high >= self.bottom and candle.low <= self.top


@dataclass(frozen=True)
class BosEvent:
    index: int
    side: Side
    level: float
    close: float
    strength: str
    body_ratio: float
    time: str
    event_type: str = "BOS"


@dataclass(frozen=True)
class M5ExecutionConfirmation:
    latest_closed_index: int | None
    latest_closed_time: str | None
    latest_event: dict[str, Any] | None
    latest_event_index: int | None
    latest_event_time: str | None
    latest_event_side: Side | None
    latest_event_type: str | None
    required_side: Side | None
    event_is_latest_close: bool
    valid: bool
    reason_codes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "latest_closed_index": self.latest_closed_index,
            "latest_closed_time": self.latest_closed_time,
            "latest_event": self.latest_event,
            "latest_event_index": self.latest_event_index,
            "latest_event_time": self.latest_event_time,
            "latest_event_side": self.latest_event_side,
            "latest_event_type": self.latest_event_type,
            "required_side": self.required_side,
            "event_is_latest_close": self.event_is_latest_close,
            "valid": self.valid,
            "reason_codes": list(self.reason_codes),
        }


@dataclass
class Decision:
    status: str
    reason_codes: list[str] = field(default_factory=list)
    side: Side | None = None
    entry_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    risk_reward: float | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def is_signal(self) -> bool:
        return self.status == "SIGNAL"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason_codes": self.reason_codes,
            "side": self.side,
            "entry_price": self.entry_price,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "risk_reward": self.risk_reward,
            "evidence": self.evidence,
        }
