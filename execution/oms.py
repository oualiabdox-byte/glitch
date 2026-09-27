"""Minimal order-management state machine for broker-confirmed execution."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class OrderState(StrEnum):
    NEW = "NEW"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


TERMINAL_STATES = frozenset({
    OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED,
    OrderState.EXPIRED, OrderState.FAILED,
})

_ALLOWED: dict[OrderState, frozenset[OrderState]] = {
    OrderState.NEW: frozenset({OrderState.SUBMITTED, OrderState.FAILED}),
    OrderState.SUBMITTED: frozenset({
        OrderState.ACKNOWLEDGED, OrderState.PARTIALLY_FILLED,
        OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED,
        OrderState.EXPIRED, OrderState.FAILED, OrderState.UNKNOWN,
    }),
    OrderState.ACKNOWLEDGED: frozenset({
        OrderState.PARTIALLY_FILLED, OrderState.FILLED,
        OrderState.CANCELLED, OrderState.REJECTED, OrderState.EXPIRED,
        OrderState.UNKNOWN,
    }),
    OrderState.PARTIALLY_FILLED: frozenset({
        OrderState.PARTIALLY_FILLED, OrderState.FILLED,
        OrderState.CANCELLED, OrderState.EXPIRED, OrderState.UNKNOWN,
    }),
    OrderState.UNKNOWN: frozenset({
        OrderState.ACKNOWLEDGED, OrderState.PARTIALLY_FILLED,
        OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED,
        OrderState.EXPIRED,
    }),
    OrderState.FILLED: frozenset(),
    OrderState.CANCELLED: frozenset(),
    OrderState.REJECTED: frozenset(),
    OrderState.EXPIRED: frozenset(),
    OrderState.FAILED: frozenset(),
}

EVENT_TO_STATE = {
    "ORDER_ACCEPTED": OrderState.ACKNOWLEDGED,
    "ORDER_PARTIAL_FILL": OrderState.PARTIALLY_FILLED,
    "ORDER_FILLED": OrderState.FILLED,
    "ORDER_CANCELLED": OrderState.CANCELLED,
    "ORDER_EXPIRED": OrderState.EXPIRED,
    "ORDER_REJECTED": OrderState.REJECTED,
}


@dataclass(frozen=True)
class OrderIntent:
    internal_order_id: str
    account_id: int | None
    symbol: str
    side: str
    requested_volume: float
    client_order_id: str


@dataclass
class OrderRecord:
    intent: OrderIntent
    state: OrderState = OrderState.NEW
    broker_order_id: int | None = None
    position_id: int | None = None
    executed_volume: float = 0.0
    remaining_volume: float | None = None
    execution_price: float | None = None
    processed_event_ids: set[str] = field(default_factory=set)
    reason: str | None = None
    error_code: str | None = None
    error_description: str | None = None


@dataclass(frozen=True)
class TransitionResult:
    applied: bool
    duplicate: bool
    internal_order_id: str
    previous_state: OrderState
    resulting_state: OrderState
    reason: str | None = None


class InvalidTransition(ValueError):
    pass


class OMS:
    """In-memory domain state; persistence is deliberately delegated to storage."""

    def __init__(self, account_id: int | None = None):
        self.account_id = account_id
        self.orders: dict[str, OrderRecord] = {}
        self.halted = False
        self.halt_reason: str | None = None

    def create_intent(self, intent: OrderIntent) -> OrderRecord:
        if self.halted:
            raise RuntimeError(f"EXECUTION_HALT: {self.halt_reason or 'account halted'}")
        if intent.internal_order_id in self.orders:
            raise ValueError(f"duplicate internal_order_id={intent.internal_order_id}")
        record = OrderRecord(intent=intent, remaining_volume=intent.requested_volume)
        self.orders[intent.internal_order_id] = record
        return record

    def mark_submitted(self, internal_order_id: str) -> TransitionResult:
        return self._transition(internal_order_id, OrderState.SUBMITTED)

    def mark_failed(self, internal_order_id: str, reason: str) -> TransitionResult:
        result = self._transition(internal_order_id, OrderState.FAILED, reason=reason)
        return result

    def mark_rejected(self, internal_order_id: str, reason: str) -> TransitionResult:
        return self._transition(internal_order_id, OrderState.REJECTED, reason=reason)

    def mark_unknown(self, internal_order_id: str, reason: str) -> TransitionResult:
        result = self._transition(internal_order_id, OrderState.UNKNOWN, reason=reason)
        self.halt(f"order {internal_order_id}: {reason}")
        return result

    def apply_broker_event(self, internal_order_id: str, event: dict[str, Any]) -> TransitionResult:
        record = self.orders[internal_order_id]
        event_id = str(event.get("event_id") or "")
        if not event_id:
            raise ValueError("broker event must have event_id for idempotency")
        if event_id in record.processed_event_ids:
            return TransitionResult(False, True, internal_order_id, record.state, record.state)

        event_type = str(event.get("execution_type") or "")
        resulting = EVENT_TO_STATE.get(event_type)
        if resulting is None:
            raise ValueError(f"unsupported broker execution_type={event_type!r}")

        if event.get("broker_order_id") is not None:
            record.broker_order_id = int(event["broker_order_id"])
        if event.get("position_id") is not None:
            record.position_id = int(event["position_id"])
        if event.get("executed_volume") is not None and float(event["executed_volume"]) > 0:
            record.executed_volume = float(event["executed_volume"])
        elif event.get("last_volume") is not None:
            record.executed_volume += float(event["last_volume"])
        record.remaining_volume = max(0.0, record.intent.requested_volume - record.executed_volume)
        if event.get("execution_price") is not None:
            record.execution_price = float(event["execution_price"])
        record.processed_event_ids.add(event_id)
        return self._transition(internal_order_id, resulting, reason=event_type)

    def halt(self, reason: str) -> None:
        self.halted = True
        self.halt_reason = reason

    def clear_halt(self) -> None:
        self.halted = False
        self.halt_reason = None

    def _transition(self, internal_order_id: str, resulting: OrderState,
                    *, reason: str | None = None) -> TransitionResult:
        record = self.orders[internal_order_id]
        previous = record.state
        if previous != resulting and resulting not in _ALLOWED[previous]:
            raise InvalidTransition(f"{previous} -> {resulting} for {internal_order_id}")
        record.state = resulting
        if reason:
            record.reason = reason
        return TransitionResult(
            applied=previous != resulting,
            duplicate=previous == resulting,
            internal_order_id=internal_order_id,
            previous_state=previous,
            resulting_state=resulting,
            reason=reason,
        )


def allowed_transitions() -> dict[str, list[str]]:
    return {state.value: sorted(next_state.value for next_state in next_states)
            for state, next_states in _ALLOWED.items()}
