"""Submit one guarded demo order through the broker-confirmed OMS path."""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any

from ctrader_open_api import Protobuf
from twisted.internet import reactor

from config.settings import load_config, risk_config
from data.ctrader import CTraderData, normalize_symbol_spec
from execution.demo_guard import require_demo_execution
from execution.oms import OMS, OrderIntent, OrderState
from execution.reconciliation import Reconciler
from execution.risk import resolve_order_volume
from execution.storage import EventStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _broker_order(row: dict[str, Any]) -> dict[str, Any]:
    trade_data = row.get("tradeData") or {}
    status = str(row.get("orderStatus", ""))
    state = {
        "ORDER_STATUS_ACCEPTED": "ACKNOWLEDGED",
        "ORDER_STATUS_FILLED": "FILLED",
        "ORDER_STATUS_REJECTED": "REJECTED",
        "ORDER_STATUS_EXPIRED": "EXPIRED",
        "ORDER_STATUS_CANCELLED": "CANCELLED",
    }.get(status, status)
    return {
        "broker_order_id": row.get("orderId"),
        "client_order_id": row.get("clientOrderId"),
        "symbol": trade_data.get("symbolId"),
        "side": trade_data.get("tradeSide"),
        "state": state,
        "executed_volume": float(row.get("executedVolume", 0) or 0) / 100.0,
    }


def _broker_position(row: dict[str, Any]) -> dict[str, Any]:
    trade_data = row.get("tradeData") or {}
    return {
        "position_id": row.get("positionId"),
        "symbol": trade_data.get("symbolId"),
        "side": trade_data.get("tradeSide"),
        "volume": float(trade_data.get("volume", 0) or 0) / 100.0,
    }


def main() -> int:
    require_demo_execution()
    if os.getenv("CTRADER_ENV", "demo").strip().lower() != "demo":
        raise RuntimeError("demo_order refuses non-demo environments")
    signal = json.load(sys.stdin)
    pair = str(signal["pair"]).upper()
    side = str(signal["side"]).upper()
    if side not in {"LONG", "SHORT", "BUY", "SELL"}:
        raise ValueError("signal side must be LONG or SHORT")
    stop = float(signal["stop_price"])
    target_value = signal.get("target_price", signal.get("tp_target"))
    target = float(target_value)
    entry = float(signal["entry_price"])
    stop_distance = abs(entry - stop)
    target_distance = abs(target - entry)
    if stop_distance <= 0 or target_distance <= 0:
        raise ValueError("signal must have positive SL and TP distances")

    config = load_config()
    risk_defaults = risk_config(config)
    feed = CTraderData()
    store = EventStore(os.getenv("CTRADER_DATABASE_PATH", "results/trading.db"))
    oms = OMS(int(os.getenv("CTRADER_ACCOUNT_ID")) if os.getenv("CTRADER_ACCOUNT_ID") else None)
    reconciler = Reconciler()
    internal_order_id = f"INT-{uuid.uuid4().hex}"
    client_order_id = f"CRT-{pair}-{uuid.uuid4().hex[:16]}"
    result = {"pair": pair, "status": "CONNECTING", "internal_order_id": internal_order_id}
    submitted = False

    def stop_reactor() -> None:
        if reactor.running:
            reactor.stop()

    def persist_state(state: OrderState, **extra: Any) -> None:
        store.record_order_state(_now(), internal_order_id, state.value, **extra)

    def broker_event(event: dict[str, Any]) -> None:
        nonlocal result
        if internal_order_id not in oms.orders:
            return
        matches = (
            event.get("client_msg_id") == internal_order_id
            or event.get("client_order_id") == client_order_id
            or (event.get("broker_order_id") is not None
                and oms.orders[internal_order_id].broker_order_id == event.get("broker_order_id"))
        )
        if not matches and event.get("kind") == "execution":
            return

        if event.get("kind") == "order_error":
            if event.get("broker_order_id") is not None:
                transition = oms.mark_rejected(
                    internal_order_id,
                    event.get("error_code") or "BROKER_ORDER_ERROR",
                )
                state = transition.resulting_state
            else:
                transition = oms.mark_failed(
                    internal_order_id,
                    f"broker rejected request without broker order: {event.get('error_code', '')}",
                )
                state = transition.resulting_state
            event["internal_order_id"] = internal_order_id
            store.record_broker_event(_now(), event, state.value)
            persist_state(state, broker_order_id=event.get("broker_order_id"),
                          position_id=event.get("position_id"),
                          reason=event.get("error_code"),
                          error_code=event.get("error_code"),
                          error_description=event.get("error_description"))
            result = {"pair": pair, "status": state.value, "internal_order_id": internal_order_id,
                      "broker_event": event}
            print(json.dumps(result, sort_keys=True), flush=True)
            stop_reactor()
            return

        if event.get("kind") == "protocol_error":
            transition = oms.mark_failed(
                internal_order_id,
                f"definitive protocol error: {event.get('error_code', '')}",
            )
            event["internal_order_id"] = internal_order_id
            store.record_broker_event(_now(), event, transition.resulting_state.value)
            persist_state(transition.resulting_state, reason=transition.reason,
                          error_code=event.get("error_code"),
                          error_description=event.get("error_description"))
            print(json.dumps({"pair": pair, "status": "FAILED",
                              "internal_order_id": internal_order_id,
                              "broker_event": event}, sort_keys=True), flush=True)
            stop_reactor()
            return

        if event.get("kind") != "execution":
            return
        event["internal_order_id"] = internal_order_id
        try:
            transition = oms.apply_broker_event(internal_order_id, event)
        except ValueError as exc:
            oms.halt(str(exc))
            store.set_execution_halt(oms.account_id or int(event.get("account_id", 0)), _now(), str(exc))
            print(json.dumps({"pair": pair, "status": "EXECUTION_HALT", "error": str(exc)}, sort_keys=True), flush=True)
            stop_reactor()
            return
        stored = store.record_broker_event(_now(), event, transition.resulting_state.value)
        if stored and not transition.duplicate:
            record = oms.orders[internal_order_id]
            persist_state(record.state, broker_order_id=record.broker_order_id,
                          position_id=record.position_id, executed_volume=record.executed_volume,
                          remaining_volume=record.remaining_volume,
                          execution_price=record.execution_price, reason=record.reason)
        result = {
            "pair": pair,
            "status": transition.resulting_state.value,
            "internal_order_id": internal_order_id,
            "broker_event": event,
            "duplicate": transition.duplicate,
        }
        print(json.dumps(result, sort_keys=True), flush=True)
        if transition.resulting_state in {OrderState.FILLED, OrderState.CANCELLED,
                                          OrderState.REJECTED, OrderState.EXPIRED}:
            stop_reactor()

    def reconciliation(snapshot: dict[str, Any]) -> None:
        account_id = int(snapshot["account_id"])
        internal = []
        for record in oms.orders.values():
            internal.append({
                "internal_order_id": record.intent.internal_order_id,
                "client_order_id": record.intent.client_order_id,
                "broker_order_id": record.broker_order_id,
                "position_id": record.position_id,
                "symbol": record.intent.symbol,
                "side": record.intent.side,
                "state": record.state.value,
                "executed_volume": record.executed_volume,
            })
        broker_orders = [_broker_order(row) for row in snapshot.get("broker_orders", [])]
        broker_positions = [_broker_position(row) for row in snapshot.get("broker_positions", [])]
        result_obj = reconciler.compare(account_id, internal, broker_orders,
                                        broker_positions)
        details = {"status": result_obj.status, "mismatches": list(result_obj.mismatches),
                   "checked_orders": result_obj.checked_orders,
                   "checked_positions": result_obj.checked_positions,
                   "raw_payload_hex": snapshot.get("raw_payload_hex")}
        store.record_reconciliation(_now(), account_id, details)
        if result_obj.halted:
            reason = "reconciliation mismatch"
            oms.halt(reason)
            store.set_execution_halt(account_id, _now(), reason)
            print(json.dumps({"status": "EXECUTION_HALT", "reconciliation": details}, sort_keys=True), flush=True)

    def transport_failed(failure: Any) -> Any:
        if submitted and not oms.orders[internal_order_id].state in {
            OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED,
            OrderState.EXPIRED, OrderState.FAILED,
        }:
            transition = oms.mark_unknown(internal_order_id, f"transport failure after send: {failure}")
            store.set_execution_halt(oms.account_id or int(os.getenv("CTRADER_ACCOUNT_ID", "0")), _now(), transition.reason or "UNKNOWN")
            persist_state(transition.resulting_state, reason=transition.reason)
            print(json.dumps({"pair": pair, "status": "UNKNOWN", "internal_order_id": internal_order_id,
                              "reason": transition.reason}, sort_keys=True), flush=True)
            stop_reactor()
        return failure

    def submit(_symbols: Any) -> None:
        nonlocal submitted
        account_id = feed.account_id
        oms.account_id = account_id
        if store.is_execution_halted(account_id):
            raise RuntimeError("EXECUTION_HALT: account is halted")
        symbol_id = feed.symbol_id(pair)
        symbol_spec = normalize_symbol_spec(feed.symbol_info(pair))
        sizing = resolve_order_volume(signal, symbol_spec, risk_defaults=risk_defaults)
        volume = sizing.volume_units
        intent = OrderIntent(internal_order_id, account_id, pair, side, volume, client_order_id)
        oms.create_intent(intent)
        store.record_order_intent(_now(), intent.__dict__)
        try:
            deferred = feed.submit_market_order(
                symbol_id, side, volume,
                relative_stop_loss=stop_distance,
                relative_take_profit=target_distance,
                client_order_id=client_order_id,
                internal_order_id=internal_order_id,
                label="CRT-DEMO",
                comment=f"CRT {signal.get('timestamp', '')}",
            )
            oms.mark_submitted(internal_order_id)
            persist_state(OrderState.SUBMITTED)
            submitted = True
            deferred.addErrback(transport_failed)
            result.update({"pair": pair, "status": "SUBMITTED", "client_order_id": client_order_id,
                           "volume_units": volume, "sizing_mode": sizing.mode})
            print(json.dumps(result, sort_keys=True), flush=True)
        except Exception as exc:
            oms.mark_failed(internal_order_id, str(exc))
            persist_state(OrderState.FAILED, reason=str(exc))
            raise

    feed.on_broker_event = broker_event
    feed.on_reconciliation = reconciliation
    feed.execution_halt_checker = lambda: feed.account_id is not None and store.is_execution_halted(feed.account_id)
    feed.on_account_ready = lambda: feed.request_symbols(submit)
    feed.connect()
    reactor.run()
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
