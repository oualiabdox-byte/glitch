"""Periodic broker-vs-internal reconciliation for the execution boundary."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class ReconciliationResult:
    account_id: int
    status: str
    mismatches: tuple[dict[str, Any], ...]
    checked_orders: int
    checked_positions: int

    @property
    def halted(self) -> bool:
        return self.status == "MISMATCH"


class Reconciler:
    """Compare normalized internal OMS records to cTrader snapshots.

    This class does not repair either side. A mismatch is recorded and must be
    handled by an explicit controlled-recovery action.
    """

    def __init__(self, symbol_normalizer=None):
        self.symbol_normalizer = symbol_normalizer

    def compare(self, account_id: int, internal_orders: Iterable[dict[str, Any]],
                broker_orders: Iterable[dict[str, Any]],
                broker_positions: Iterable[dict[str, Any]]) -> ReconciliationResult:
        internal = {self._key(row): row for row in internal_orders}
        broker = {self._key(row): row for row in broker_orders}
        mismatches: list[dict[str, Any]] = []

        for key, row in internal.items():
            if key not in broker and row.get("state") not in {
                "FILLED", "CANCELLED", "REJECTED", "EXPIRED", "FAILED",
            }:
                mismatches.append({"type": "MISSING_BROKER_ORDER", "key": key})
                continue
            if key in broker:
                b = broker[key]
                for field in ("broker_order_id", "executed_volume", "state"):
                    if row.get(field) is not None and b.get(field) is not None and row.get(field) != b.get(field):
                        mismatches.append({"type": "ORDER_FIELD_MISMATCH", "key": key,
                                           "field": field, "internal": row.get(field),
                                           "broker": b.get(field)})

        internal_positions = {
            self._position_key(row): float(row.get("executed_volume", 0) or 0)
            for row in internal_orders
            if row.get("position_id") is not None
        }
        broker_position_totals = {
            self._position_key(row): float(row.get("volume", 0) or 0)
            for row in broker_positions
        }
        for key, volume in internal_positions.items():
            if broker_position_totals.get(key, 0.0) != volume:
                mismatches.append({"type": "POSITION_VOLUME_MISMATCH", "key": key,
                                   "internal": volume, "broker": broker_position_totals.get(key, 0.0)})
        for key, volume in broker_position_totals.items():
            if key not in internal_positions and volume:
                mismatches.append({"type": "UNEXPECTED_BROKER_POSITION", "key": key,
                                   "broker": volume})

        return ReconciliationResult(
            account_id=int(account_id),
            status="MISMATCH" if mismatches else "MATCH",
            mismatches=tuple(mismatches),
            checked_orders=len(internal),
            checked_positions=len(broker_position_totals),
        )

    def _symbol(self, value: Any) -> Any:
        if self.symbol_normalizer is None:
            return value
        return self.symbol_normalizer(value)

    def _key(self, row: dict[str, Any]) -> str:
        if row.get("broker_order_id") is not None:
            return f"broker:{row['broker_order_id']}"
        if row.get("client_order_id"):
            return f"client:{row['client_order_id']}"
        return f"internal:{row.get('internal_order_id')}"

    def _position_key(self, row: dict[str, Any]) -> tuple[Any, Any]:
        return self._symbol(row.get("symbol")), row.get("side")
