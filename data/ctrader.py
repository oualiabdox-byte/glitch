"""cTrader historical OHLC data provider for the Forex strategy.

Broker boundary for historical backtests. Uses Spotware's official Python SDK.
No MT5, Kraken, B2TRADER, or hard-coded broker symbol IDs.
Credentials are read only from environment/OpenClaw secret injection.

The provider:
- discovers symbol IDs from cTrader's symbol list
- converts cTrader relative trendbar prices correctly
- paginates historical H1/H4 requests
- rate-limits historical requests below cTrader's documented limit
- caches downloaded data for repeatable backtests
"""
from __future__ import annotations

import datetime as _dt
import json
import time
from pathlib import Path
from typing import Any, Callable, Optional

from ctrader_open_api import Protobuf
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOASymbolsListReq,
    ProtoOASymbolsListRes,
    ProtoOAGetTrendbarsReq,
    ProtoOAGetTrendbarsRes,
)
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOATrendbarPeriod
from twisted.internet import reactor

from execution.ctrader_adapter import CTraderAdapter


PERIODS = {
    "m1": "M1", "m5": "M5", "m15": "M15", "m30": "M30",
    "h1": "H1", "h4": "H4", "d1": "D1",
}

# cTrader documents a maximum of 5 historical requests/second/connection.
# Keep a safety margin rather than running exactly at the limit.
_HISTORY_MIN_INTERVAL = 0.25
_DEFAULT_PAGE_SIZE = 1000


def _period_enum(period: str):
    name = PERIODS[period.lower()]
    return getattr(ProtoOATrendbarPeriod, name)


def _period_name(value) -> str:
    try:
        return ProtoOATrendbarPeriod.Name(value).lower()
    except Exception:
        return str(value).lower()


def _ms(value) -> int:
    if isinstance(value, (int, float)):
        return int(value * 1000) if value < 10_000_000_000 else int(value)
    if isinstance(value, _dt.datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=_dt.timezone.utc)
    else:
        dt = _dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return int(dt.timestamp() * 1000)


def _iso_ms(ms: int) -> str:
    return _dt.datetime.fromtimestamp(ms / 1000, tz=_dt.timezone.utc).isoformat()


def _normalize_symbol(name: str) -> str:
    return (
        name.replace("/", "").replace("_", "").replace("-", "")
        .replace(".", "").upper()
    )


def normalize_symbol_spec(symbol: Any) -> dict[str, Any]:
    """Convert cTrader symbol volume fields from protocol cents to units.

    cTrader represents volume and lot size in 0.01 units in Open API messages.
    Strategy/risk code works in normal base-currency units.
    """
    def units(name: str) -> float:
        return float(getattr(symbol, name, 0) or 0) / 100.0

    return {
        "symbolId": int(getattr(symbol, "symbolId", 0)),
        "digits": int(getattr(symbol, "digits", 0)),
        "pipPosition": int(getattr(symbol, "pipPosition", 0)),
        "lotSize": units("lotSize"),
        "minVolume": units("minVolume"),
        "maxVolume": units("maxVolume"),
        "stepVolume": units("stepVolume"),
        "commission": float(getattr(symbol, "commission", 0) or 0),
        "commissionType": int(getattr(symbol, "commissionType", 0) or 0),
        "pnlConversionFeeRate": float(
            getattr(symbol, "pnlConversionFeeRate", 0) or 0
        ),
    }


def trendbars_to_ohlc(trendbars, digits: Optional[int] = None) -> list[dict[str, Any]]:
    """Convert cTrader's relative trendbar representation to ordinary OHLC."""
    rows = []
    for bar in trendbars:
        low_raw = int(bar.low)
        scale = 100000.0

        def price(raw: int) -> float:
            value = raw / scale
            return round(value, int(digits)) if digits is not None else value

        rows.append({
            "time": _iso_ms(int(bar.utcTimestampInMinutes) * 60 * 1000),
            "open": price(low_raw + int(bar.deltaOpen)),
            "high": price(low_raw + int(bar.deltaHigh)),
            "low": price(low_raw),
            "close": price(low_raw + int(bar.deltaClose)),
            "volume": int(getattr(bar, "volume", 0)),
        })
    return sorted(rows, key=lambda x: x["time"])


class CTraderData(CTraderAdapter):
    """Historical market-data layer built on the cTrader adapter."""

    def __init__(self, config=None, cache_dir: str = "data/ctrader_cache"):
        super().__init__(config)
        self.symbols: dict[str, Any] = {}
        self._symbol_waiters: list[Callable] = []
        self._history_waiters: list[dict[str, Any]] = []
        self._history_last_sent = 0.0
        self.cache_dir = Path(cache_dir)

    def request_symbols(self, callback: Optional[Callable] = None) -> None:
        if callback:
            self._symbol_waiters.append(callback)
        req = ProtoOASymbolsListReq()
        req.ctidTraderAccountId = self._require_account()
        req.includeArchivedSymbols = False
        self._send(req)

    def symbol_id(self, name: str) -> int:
        target = _normalize_symbol(name)
        for key, value in self.symbols.items():
            if _normalize_symbol(key) == target:
                return int(value.symbolId)
        raise KeyError(
            f"cTrader symbol {name!r} not found. "
            f"Available sample: {', '.join(list(self.symbols)[:30])}"
        )

    def symbol_info(self, name: str) -> Any:
        target = _normalize_symbol(name)
        for key, value in self.symbols.items():
            if _normalize_symbol(key) == target:
                return value
        raise KeyError(f"cTrader symbol {name!r} not found")

    def history_async(
        self,
        symbol_id: int,
        period: str,
        start,
        end,
        count: int = _DEFAULT_PAGE_SIZE,
        callback: Optional[Callable] = None,
    ):
        """Request one historical page. Pagination is handled by download()."""
        period = period.lower()
        if period not in PERIODS:
            raise ValueError(f"Unsupported cTrader period: {period}")

        elapsed = time.monotonic() - self._history_last_sent
        if elapsed < _HISTORY_MIN_INTERVAL:
            reactor.callLater(
                _HISTORY_MIN_INTERVAL - elapsed,
                self.history_async, symbol_id, period, start, end, count, callback
            )
            return None

        req = ProtoOAGetTrendbarsReq()
        req.ctidTraderAccountId = self._require_account()
        req.symbolId = int(symbol_id)
        req.period = _period_enum(period)
        req.fromTimestamp = _ms(start)
        req.toTimestamp = _ms(end)
        req.count = int(count)

        self._history_last_sent = time.monotonic()
        self._history_waiters.append({
            "symbol_id": int(symbol_id),
            "period": period,
            "callback": callback,
        })
        return self._send(req)

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
            for callback in waiters:
                callback(self.symbols)
            return

        if payload_type == ProtoOAGetTrendbarsRes().payloadType:
            response = Protobuf.extract(message)
            sid = int(response.symbolId)
            period = _period_name(response.period)
            waiter = next(
                (x for x in self._history_waiters
                 if x["symbol_id"] == sid and x["period"] == period),
                None,
            )
            if waiter:
                self._history_waiters.remove(waiter)
                info = self.symbols.get(
                    next((k for k, v in self.symbols.items()
                          if int(getattr(v, "symbolId", -1)) == sid), ""),
                    None,
                )
                digits = getattr(info, "digits", None) if info is not None else None
                candles = trendbars_to_ohlc(response.trendbar, digits)
                waiter["callback"](candles, bool(getattr(response, "hasMore", False)))
            return

        super()._on_message(client, message)

    def _cache_path(self, symbol: str, start, end, periods: tuple[str, ...]) -> Path:
        start_ms, end_ms = _ms(start), _ms(end)
        key = (
            f"{_normalize_symbol(symbol)}_"
            f"{start_ms}_{end_ms}_"
            f"{'-'.join(sorted(periods))}.json"
        )
        return self.cache_dir / key

    def download(
        self,
        symbol: str,
        start,
        end,
        periods=("h1", "h4"),
        use_cache: bool = True,
    ) -> dict[str, list[dict]]:
        """Download complete historical data for a backtest.

        The cTrader API returns pages ending at toTimestamp. We walk backwards
        from end until the requested start is covered, then sort/deduplicate.
        """
        requested = tuple(p.lower() for p in periods)
        for p in requested:
            if p not in PERIODS:
                raise ValueError(f"Unsupported cTrader period: {p}")

        cache = self._cache_path(symbol, start, end, requested)
        if use_cache and cache.exists():
            return json.loads(cache.read_text())

        result: dict[str, list[dict]] = {p: [] for p in requested}
        errors: list[BaseException] = []
        state = {
            "pending": list(requested),
            "sid": None,
            "start_ms": _ms(start),
            "end_ms": _ms(end),
            "symbol": symbol,
        }

        def fail(exc: BaseException):
            errors.append(exc)
            if reactor.running:
                reactor.callLater(0, reactor.stop)

        def after_symbols(_symbols):
            try:
                state["sid"] = self.symbol_id(symbol)
                _request_next()
            except BaseException as exc:
                fail(exc)

        def _request_next():
            if not state["pending"]:
                for p in result:
                    # Stable chronological order and duplicate protection.
                    unique = {c["time"]: c for c in result[p]}
                    result[p] = [unique[k] for k in sorted(unique)]
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                cache.write_text(json.dumps(result, indent=2))
                reactor.callLater(0, reactor.stop)
                return

            period = state["pending"][0]
            cursor_end = state.get(f"{period}_cursor_end", state["end_ms"])

            def received(candles, has_more):
                if not candles:
                    state["pending"].pop(0)
                    _request_next()
                    return

                result[period].extend(candles)
                earliest = min(_ms(c["time"]) for c in candles)

                # Some cTrader responses omit/under-report hasMore when the
                # page is exactly full. Continue paging while a full page
                # still ends after the requested start; the following request
                # will return an empty page if the server has no more data.
                page_is_full = len(candles) >= _DEFAULT_PAGE_SIZE
                if earliest <= state["start_ms"] or (not has_more and not page_is_full):
                    state["pending"].pop(0)
                    _request_next()
                    return

                # Move the next request strictly before the earliest returned bar.
                state[f"{period}_cursor_end"] = earliest - 1
                reactor.callLater(
                    _HISTORY_MIN_INTERVAL,
                    lambda: self.history_async(
                        state["sid"], period, state["start_ms"],
                        state[f"{period}_cursor_end"],
                        callback=received,
                    ),
                )

            self.history_async(
                state["sid"], period, state["start_ms"], cursor_end,
                callback=received,
            )

        self._symbol_waiters.append(after_symbols)
        self.connect()
        reactor.run()

        if errors:
            raise errors[0]
        return result
