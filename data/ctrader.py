"""cTrader historical OHLC data provider for the Forex strategy.

Uses Spotware's official Python SDK. No MT5, Kraken, or B2TRADER dependency.
Credentials are read from the environment/OpenClaw secret injection path.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any

from ctrader_open_api import Protobuf
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOASymbolsListReq,
    ProtoOASymbolsListRes,
    ProtoOAGetTrendbarsReq,
    ProtoOAGetTrendbarsRes,
    ProtoOATrendbarPeriod,
)

from execution.ctrader_adapter import CTraderAdapter
from twisted.internet import reactor


PERIODS = {
    "m1": "M1", "m5": "M5", "m15": "M15", "m30": "M30",
    "h1": "H1", "h4": "H4", "d1": "D1",
}


class CTraderData(CTraderAdapter):
    """Read-only historical market-data layer built on the cTrader adapter."""

    def __init__(self, config=None):
        super().__init__(config)
        self.symbols: dict[str, Any] = {}
        self._symbol_waiters: list[Any] = []
        self._history_waiters: list[Any] = []

    def request_symbols(self, callback=None) -> None:
        if callback:
            self._symbol_waiters.append({"callback": callback})
        req = ProtoOASymbolsListReq()
        req.ctidTraderAccountId = self._require_account()
        req.includeArchivedSymbols = False
        self._send(req)

    def history_async(self, symbol_id: int, period: str, start, end, count: int = 0, callback=None):
        period = period.lower()
        if period not in PERIODS:
            raise ValueError(f"Unsupported cTrader period: {period}")
        req = ProtoOAGetTrendbarsReq()
        req.ctidTraderAccountId = self._require_account()
        req.symbolId = int(symbol_id)
        req.period = getattr(ProtoOATrendbarPeriod, PERIODS[period])
        req.fromTimestamp = _ms(start)
        req.toTimestamp = _ms(end)
        if count:
            req.count = int(count)
        self._history_waiters.append({
            "symbol_id": int(symbol_id),
            "period": period,
            "callback": callback,
        })
        return self._send(req)

    def symbol_id(self, name: str) -> int:
        target = name.replace("/", "").replace("_", "").upper()
        for key, value in self.symbols.items():
            normalized = key.replace("/", "").replace("_", "").upper()
            if normalized == target:
                return int(getattr(value, "symbolId"))
        raise KeyError(
            f"cTrader symbol {name!r} not found. Available: "
            + ", ".join(list(self.symbols)[:30])
        )

    def _on_message(self, client, message):
        payload_type = getattr(message, "payloadType", None)

        if payload_type == ProtoOASymbolsListRes().payloadType:
            response = Protobuf.extract(message)
            self.symbols = {
                str(getattr(s, "symbolName", "")): s
                for s in response.symbol
                if getattr(s, "symbolName", "")
            }
            print(f"[cTrader] loaded {len(self.symbols)} symbols")
            waiters, self._symbol_waiters = self._symbol_waiters, []
            for waiter in waiters:
                waiter["callback"](self.symbols)
            return

        if payload_type == ProtoOAGetTrendbarsRes().payloadType:
            response = Protobuf.extract(message)
            waiter = next(
                (x for x in self._history_waiters
                 if x["symbol_id"] == int(response.symbolId)
                 and x["period"] == _period_name(response.period)),
                None,
            )
            if waiter:
                self._history_waiters.remove(waiter)
                candles = trendbars_to_ohlc(response.trendbar)
                if waiter["callback"]:
                    waiter["callback"](candles)
            return

        super()._on_message(client, message)

    def download(self, symbol: str, start, end, periods=("h1", "h4")) -> dict[str, list[dict]]:
        """Blocking convenience API for backtests; stops the Twisted reactor after all data arrives."""
        result: dict[str, list[dict]] = {}
        errors: list[BaseException] = []
        requested = tuple(p.lower() for p in periods)

        def after_symbols(_symbols):
            try:
                sid = self.symbol_id(symbol)
                for period in requested:
                    self.history_async(
                        sid, period, start, end,
                        callback=lambda candles, p=period: _received(p, candles),
                    )
            except BaseException as exc:
                errors.append(exc)
                if reactor.running:
                    reactor.stop()

        def _received(period, candles):
            result[period] = candles
            if len(result) == len(requested) and reactor.running:
                reactor.callLater(0, reactor.stop)

        def on_connected(_client):
            # App/account auth is performed by the base adapter. Symbols are
            # requested after account auth, not before it.
            pass

        self._symbol_waiters.append({"callback": after_symbols})
        self.connect()
        self._on_connected = super()._on_connected
        # Account-auth callback in the base adapter calls request_account_state,
        # which includes ProtoOASymbolsListReq. Our symbols handler receives it.
        reactor.run()
        if errors:
            raise errors[0]
        missing = [p for p in requested if p not in result]
        if missing:
            raise RuntimeError(f"cTrader returned no historical data for {missing}")
        return result


def _period_name(value) -> str:
    try:
        name = ProtoOATrendbarPeriod.Name(value)
    except Exception:
        return str(value)
    return name.lower()


def _ms(value) -> int:
    if isinstance(value, (int, float)):
        return int(value * 1000) if value < 10_000_000_000 else int(value)
    if isinstance(value, _dt.datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=_dt.timezone.utc)
    else:
        text = str(value).replace("Z", "+00:00")
        dt = _dt.datetime.fromisoformat(text)
    return int(dt.timestamp() * 1000)


def trendbars_to_ohlc(trendbars):
    rows = []
    for bar in trendbars:
        low = float(bar.low) / 100000.0
        rows.append({
            "time": _dt.datetime.fromtimestamp(
                int(bar.utcTimestampInMinutes) * 60,
                tz=_dt.timezone.utc,
            ).isoformat(),
            "open": (float(bar.low) + float(bar.deltaOpen)) / 100000.0,
            "high": (float(bar.low) + float(bar.deltaHigh)) / 100000.0,
            "low": low,
            "close": (float(bar.low) + float(bar.deltaClose)) / 100000.0,
            "volume": int(getattr(bar, "volume", 0)),
        })
    return sorted(rows, key=lambda x: x["time"])
