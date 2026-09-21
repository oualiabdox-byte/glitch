"""B2TRADER public market-data client.

Read-only guest endpoints are used for backtesting, so no credentials are
required. The tenant hostname is configurable because B2TRADER API paths are
relative to the broker's hostname.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


TIMEFRAME_MINUTES = {
    "1m": 1, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "4h": 240, "12h": 720,
    "1d": 1440, "1w": 10080, "1mo": 43200,
}

# B2TRADER guest-history maximum request windows from the official docs.
MAX_WINDOW_DAYS = {
    "1m": 30, "5m": 30, "15m": 30, "30m": 30,
    "1h": 365, "4h": 365, "12h": 365,
    "1d": 365 * 5, "1w": 365 * 5, "1mo": 365 * 5,
}


class B2TRADERError(RuntimeError):
    pass


def _utc(value):
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso(value):
    return _utc(value).isoformat().replace("+00:00", "Z")


class B2TRADERGuestData:
    """Read-only B2TRADER guest market-data access."""

    def __init__(self, base_url: str, cache_dir="data/b2trader_cache", timeout=30):
        if not base_url:
            raise ValueError("B2TRADER_BASE_URL is required")
        self.base_url = base_url.rstrip("/")
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout

    def _get_json(self, path, params=None):
        query = urlencode(params or {})
        url = f"{self.base_url}{path}" + (f"?{query}" if query else "")
        req = Request(url, headers={"User-Agent": "forex-bot/b2trader-readonly"})
        try:
            with urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:1000]
            raise B2TRADERError(f"GET {path} failed: HTTP {exc.code}: {body}") from exc
        except URLError as exc:
            raise B2TRADERError(f"GET {path} failed: {exc.reason}") from exc

    def markets(self):
        """Return active guest-visible markets."""
        return self._get_json("/frontoffice/api/v5/guest/markets")

    def market(self, market_id):
        return self._get_json(
            f"/frontoffice/api/v5/guest/markets/{quote(market_id, safe='')}"
        )

    @staticmethod
    def _extract_rows(payload):
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            raise B2TRADERError("Unexpected history response type")

        for key in ("candles", "data", "items", "history", "bars", "klines"):
            value = payload.get(key)
            if isinstance(value, list):
                return value

        # Some APIs wrap the payload one level deeper.
        for value in payload.values():
            if isinstance(value, dict):
                try:
                    return B2TRADERGuestData._extract_rows(value)
                except B2TRADERError:
                    pass
        raise B2TRADERError(
            "Could not locate candle array in B2TRADER history response"
        )

    @staticmethod
    def _candle(row):
        if isinstance(row, dict):
            # Accept documented/typical OHLC field names without inventing data.
            ts = row.get("time", row.get("timestamp", row.get("start")))
            o = row.get("open")
            h = row.get("high")
            l = row.get("low")
            c = row.get("close")
            v = row.get("volume")
        elif isinstance(row, (list, tuple)) and len(row) >= 5:
            ts, o, h, l, c = row[:5]
            v = row[5] if len(row) > 5 else None
        else:
            raise B2TRADERError(f"Unsupported candle row: {row!r}")

        if ts is None or any(x is None for x in (o, h, l, c)):
            raise B2TRADERError(f"Incomplete candle row: {row!r}")

        if isinstance(ts, (int, float)):
            # B2TRADER examples use ISO timestamps elsewhere; tolerate Unix
            # seconds/milliseconds for normalization only.
            ts = float(ts)
            if ts > 10_000_000_000:
                ts /= 1000.0
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        else:
            dt = _utc(ts)

        return {
            "time": dt.isoformat(),
            "open": float(o),
            "high": float(h),
            "low": float(l),
            "close": float(c),
            "volume": None if v is None else float(v),
        }

    @staticmethod
    def _validate(candles):
        candles = sorted(candles, key=lambda x: x["time"])
        clean = []
        last = None
        for c in candles:
            if c["open"] <= 0 or c["high"] <= 0 or c["low"] <= 0 or c["close"] <= 0:
                raise B2TRADERError(f"Non-positive candle: {c}")
            if c["high"] < max(c["open"], c["close"]) or c["low"] > min(c["open"], c["close"]):
                raise B2TRADERError(f"Invalid OHLC relationship: {c}")
            if last is not None and c["time"] == last:
                continue
            clean.append(c)
            last = c["time"]
        return clean

    def history(self, market_symbol, timeframe, start, end):
        """Fetch one API-compliant history window."""
        tf = timeframe.lower()
        if tf not in TIMEFRAME_MINUTES:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        start_dt, end_dt = _utc(start), _utc(end)
        if not start_dt < end_dt:
            raise ValueError("start must be before end")

        days = (end_dt - start_dt).total_seconds() / 86400
        if days > MAX_WINDOW_DAYS[tf]:
            raise ValueError(
                f"{tf} request is {days:.1f} days; maximum is "
                f"{MAX_WINDOW_DAYS[tf]} days"
            )

        params = {
            "type": tf,
            "startDate": _iso(start_dt),
            "endDate": _iso(end_dt),
        }
        payload = self._get_json(
            f"/marketdata/api/v4/guest/instruments/"
            f"{quote(market_symbol, safe='')}/history",
            params,
        )
        return self._validate([self._candle(r) for r in self._extract_rows(payload)])

    def history_chunked(self, market_symbol, timeframe, start, end):
        """Download a complete period by respecting B2TRADER window limits."""
        tf = timeframe.lower()
        if tf not in TIMEFRAME_MINUTES:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        start_dt, end_dt = _utc(start), _utc(end)
        chunk_days = MAX_WINDOW_DAYS[tf]
        # Keep a small overlap so boundary candles are not lost; validation
        # deduplicates them.
        step_seconds = max(1, chunk_days * 86400 - TIMEFRAME_MINUTES[tf] * 60)
        cursor = start_dt
        all_rows = []
        while cursor < end_dt:
            chunk_end = min(end_dt, cursor + __import__("datetime").timedelta(seconds=step_seconds))
            all_rows.extend(self.history(market_symbol, tf, cursor, chunk_end))
            if chunk_end >= end_dt:
                break
            cursor = chunk_end
            time.sleep(0.05)
        return self._validate(all_rows)

    def cached_history(self, market_symbol, timeframe, start, end, refresh=False):
        key = f"{market_symbol.replace('/', '_').replace('.', '_')}_{timeframe}_{_iso(start)}_{_iso(end)}"
        path = self.cache / (key.replace(":", "-") + ".json")
        if path.exists() and not refresh:
            return json.loads(path.read_text())
        rows = self.history_chunked(market_symbol, timeframe, start, end)
        path.write_text(json.dumps(rows, indent=2))
        return rows
