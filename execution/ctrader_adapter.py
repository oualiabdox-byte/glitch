"""cTrader Open API connection and account adapter.

This module is the broker/data boundary. Strategy logic remains in strategy/.
Secrets are read only from the environment/OpenClaw secret injection path.

The implementation follows Spotware's official Python SDK flow:
application auth -> account list by access token -> account auth.
Order submission is explicitly gated by CTRADER_ALLOW_ORDERS. The selected
environment (demo/live) controls which cTrader endpoint is used.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

from ctrader_open_api import Client, Protobuf, TcpProtocol, EndPoints
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAAccountAuthReq,
    ProtoOAApplicationAuthReq,
    ProtoOAGetAccountListByAccessTokenReq,
    ProtoOAGetAccountListByAccessTokenRes,
    ProtoOAApplicationAuthRes,
    ProtoOAAccountAuthRes,
    ProtoOASymbolsListReq,
    ProtoOATraderReq,
    ProtoOAReconcileReq,
    ProtoOASubscribeSpotsReq,
    ProtoOANewOrderReq,
    ProtoOAAmendPositionSLTPReq,
    ProtoOAClosePositionReq,
    ProtoOAOrderType,
    ProtoOATradeSide,
)
from twisted.internet import reactor


@dataclass(frozen=True)
class CTraderConfig:
    client_id: str
    client_secret: str
    access_token: str
    environment: str = "demo"
    account_id: Optional[int] = None
    allow_orders: bool = False

    @classmethod
    def from_env(cls) -> "CTraderConfig":
        def required(name: str) -> str:
            value = os.getenv(name, "").strip()
            if not value:
                raise RuntimeError(f"{name} is required")
            return value

        environment = os.getenv("CTRADER_ENV", "demo").strip().lower()
        if environment not in {"demo", "live"}:
            raise RuntimeError("CTRADER_ENV must be demo or live")

        account_raw = os.getenv("CTRADER_ACCOUNT_ID", "").strip()
        return cls(
            client_id=required("CTRADER_CLIENT_ID"),
            client_secret=required("CTRADER_CLIENT_SECRET"),
            access_token=required("CTRADER_ACCESS_TOKEN"),
            environment=environment,
            account_id=int(account_raw) if account_raw else None,
            allow_orders=os.getenv("CTRADER_ALLOW_ORDERS", "false").lower() == "true",
        )


class CTraderAdapter:
    """Thin cTrader API boundary; never decides BUY/SELL."""

    def __init__(self, config: Optional[CTraderConfig] = None):
        self.config = config or CTraderConfig.from_env()
        self.client = None
        self.account_id = self.config.account_id
        self._deferreds: list[Any] = []

    @property
    def host(self) -> str:
        return (
            EndPoints.PROTOBUF_LIVE_HOST
            if self.config.environment == "live"
            else EndPoints.PROTOBUF_DEMO_HOST
        )

    @property
    def port(self) -> int:
        return EndPoints.PROTOBUF_PORT

    def describe(self) -> dict[str, Any]:
        return {
            "broker": "cTrader",
            "environment": self.config.environment,
            "host": self.host,
            "port": self.port,
            "account_id": self.account_id,
            "order_submission": self.config.allow_orders,
        }

    def connect(self) -> None:
        """Start the SDK service and authenticate the app/account asynchronously."""
        self.client = Client(self.host, self.port, TcpProtocol)
        self.client.setConnectedCallback(self._on_connected)
        self.client.setDisconnectedCallback(self._on_disconnected)
        self.client.setMessageReceivedCallback(self._on_message)
        self.client.startService()

    def run(self) -> None:
        if self.client is None:
            self.connect()
        reactor.run()

    def stop(self) -> None:
        if reactor.running:
            reactor.stop()

    def _send(self, request: Any) -> Any:
        if self.client is None:
            raise RuntimeError("cTrader client is not connected")
        deferred = self.client.send(request)
        deferred.addErrback(self._on_error)
        self._deferreds.append(deferred)
        return deferred

    def _on_connected(self, _client: Any) -> None:
        request = ProtoOAApplicationAuthReq()
        request.clientId = self.config.client_id
        request.clientSecret = self.config.client_secret
        self._send(request)

    def _on_disconnected(self, _client: Any, reason: Any) -> None:
        print(f"[cTrader] disconnected: {reason}")

    def _on_error(self, failure: Any) -> Any:
        print(f"[cTrader] API error: {failure}")
        return failure

    def _on_message(self, _client: Any, message: Any) -> None:
        payload_type = getattr(message, "payloadType", None)

        if payload_type == ProtoOAApplicationAuthRes().payloadType:
            print("[cTrader] application authorized")
            req = ProtoOAGetAccountListByAccessTokenReq()
            req.accessToken = self.config.access_token
            self._send(req)
            return

        if payload_type == ProtoOAGetAccountListByAccessTokenRes().payloadType:
            response = Protobuf.extract(message)
            accounts = list(response.ctidTraderAccount)
            if not accounts:
                raise RuntimeError("cTrader returned no accounts for this access token")

            ids = [int(a.ctidTraderAccountId) for a in accounts]
            if self.account_id is None:
                self.account_id = ids[0]
            elif self.account_id not in ids:
                raise RuntimeError(
                    f"CTRADER_ACCOUNT_ID={self.account_id} is not in authorized accounts {ids}"
                )

            req = ProtoOAAccountAuthReq()
            req.ctidTraderAccountId = self.account_id
            req.accessToken = self.config.access_token
            self._send(req)
            return

        if payload_type == ProtoOAAccountAuthRes().payloadType:
            response = Protobuf.extract(message)
            self.account_id = int(response.ctidTraderAccountId)
            print(f"[cTrader] account authorized: {self.account_id}")
            self.request_account_state()
            return

        print(f"[cTrader] message: {Protobuf.extract(message)}")

    def _require_account(self) -> int:
        if self.account_id is None:
            raise RuntimeError("cTrader account is not authorized yet")
        return self.account_id

    def request_account_state(self) -> None:
        account_id = self._require_account()

        trader = ProtoOATraderReq()
        trader.ctidTraderAccountId = account_id
        self._send(trader)

        symbols = ProtoOASymbolsListReq()
        symbols.ctidTraderAccountId = account_id
        symbols.includeArchivedSymbols = False
        self._send(symbols)

        reconcile = ProtoOAReconcileReq()
        reconcile.ctidTraderAccountId = account_id
        self._send(reconcile)

    def subscribe_spots(self, symbol_id: int) -> None:
        request = ProtoOASubscribeSpotsReq()
        request.ctidTraderAccountId = self._require_account()
        request.symbolId.append(int(symbol_id))
        request.subscribeToSpotTimestamp = True
        self._send(request)

    def _require_order_permission(self) -> None:
        if not self.config.allow_orders:
            raise RuntimeError(
                "Order submission is disabled. Set CTRADER_ALLOW_ORDERS=true "
                "only when you intentionally want execution in the selected "
                f"CTRADER_ENV={self.config.environment!r} environment."
            )

    def submit_market_order(
        self,
        symbol_id: int,
        side: str,
        volume_units: float,
        *,
        client_order_id: Optional[str] = None,
        label: Optional[str] = None,
        comment: Optional[str] = None,
    ) -> Any:
        """Submit a market order to the selected cTrader environment.

        Strategy code supplies the direction and size; this adapter only
        translates them into cTrader protocol fields. Protective SL/TP should
        be applied after the fill via amend_position_protection because cTrader
        does not support absolute SL/TP fields on MARKET orders.
        """
        self._require_order_permission()
        if volume_units <= 0:
            raise ValueError("volume_units must be > 0")

        normalized_side = str(side).upper()
        if normalized_side not in {"BUY", "SELL", "LONG", "SHORT"}:
            raise ValueError("side must be BUY/SELL/LONG/SHORT")
        trade_side = (
            ProtoOATradeSide.Value("BUY")
            if normalized_side in {"BUY", "LONG"}
            else ProtoOATradeSide.Value("SELL")
        )

        req = ProtoOANewOrderReq()
        req.ctidTraderAccountId = self._require_account()
        req.symbolId = int(symbol_id)
        req.orderType = ProtoOAOrderType.Value("MARKET")
        req.tradeSide = trade_side
        req.volume = int(round(float(volume_units) * 100))
        if client_order_id:
            req.clientOrderId = str(client_order_id)[:50]
        if label:
            req.label = str(label)[:100]
        if comment:
            req.comment = str(comment)[:512]
        return self._send(req)

    def amend_position_protection(
        self,
        position_id: int,
        *,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        trailing_stop_loss: bool = False,
    ) -> Any:
        self._require_order_permission()
        req = ProtoOAAmendPositionSLTPReq()
        req.ctidTraderAccountId = self._require_account()
        req.positionId = int(position_id)
        if stop_loss is not None:
            req.stopLoss = float(stop_loss)
        if take_profit is not None:
            req.takeProfit = float(take_profit)
        req.trailingStopLoss = bool(trailing_stop_loss)
        return self._send(req)

    def close_position(self, position_id: int, volume_units: float) -> Any:
        self._require_order_permission()
        if volume_units <= 0:
            raise ValueError("volume_units must be > 0")
        req = ProtoOAClosePositionReq()
        req.ctidTraderAccountId = self._require_account()
        req.positionId = int(position_id)
        req.volume = int(round(float(volume_units) * 100))
        return self._send(req)

    def assert_orders_disabled(self) -> None:
        if self.config.allow_orders:
            return
