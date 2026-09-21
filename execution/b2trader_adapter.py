"""B2TRADER CFD execution adapter.

Live order submission is intentionally disabled by default. Authentication is
implemented from the official B2TRADER two-step token flow, but this module
does not submit an order unless B2TRADER_LIVE_TRADING=true is explicitly set.
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class B2TRADERExecutionError(RuntimeError):
    pass


class B2TRADERAdapter:
    def __init__(self, base_url=None, account_id=None, offline_token=None):
        self.base_url = (base_url or os.getenv("B2TRADER_BASE_URL", "")).rstrip("/")
        self.account_id = account_id or os.getenv("B2TRADER_ACCOUNT_ID")
        self.offline_token = offline_token or os.getenv("B2TRADER_OFFLINE_TOKEN")
        self.access_token = None
        self.live_enabled = os.getenv("B2TRADER_LIVE_TRADING", "false").lower() == "true"
        if not self.base_url:
            raise ValueError("B2TRADER_BASE_URL is required")

    def _request(self, method, path, body=None, authenticated=True):
        headers = {
            "Accept": "application/json",
            "User-Agent": "forex-bot/b2trader",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        if authenticated:
            if not self.access_token:
                self.refresh_access_token()
            headers["Authorization"] = f"Bearer {self.access_token}"
            if self.account_id:
                headers["accountId"] = self.account_id

        req = Request(
            f"{self.base_url}{path}",
            data=None if body is None else json.dumps(body).encode(),
            method=method,
            headers=headers,
        )
        try:
            with urlopen(req, timeout=20) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")[:1000]
            raise B2TRADERExecutionError(
                f"{method} {path} failed: HTTP {exc.code}: {body_text}"
            ) from exc
        except URLError as exc:
            raise B2TRADERExecutionError(
                f"{method} {path} failed: {exc.reason}"
            ) from exc

    def refresh_access_token(self):
        if not self.offline_token:
            raise B2TRADERExecutionError("B2TRADER_OFFLINE_TOKEN is not configured")
        payload = self._request(
            "POST",
            "/frontoffice/api/v4/access-token",
            {"token": self.offline_token},
            authenticated=False,
        )
        token = payload.get("accessToken")
        if not token:
            raise B2TRADERExecutionError("B2TRADER access token missing from response")
        self.access_token = token
        return payload

    def accounts(self):
        return self._request("GET", "/frontoffice/api/v3/accounts")

    def markets(self):
        return self._request("GET", "/frontoffice/api/v6/markets")

    def market(self, market_id):
        from urllib.parse import quote
        return self._request(
            "GET",
            f"/frontoffice/api/v6/markets/{quote(market_id, safe='')}",
        )

    def order_data(self, order):
        return self._request("POST", "/frontoffice/api/cfd/v4/order-data", {"order": order})

    def place_cfd_order(self, order):
        if not self.live_enabled:
            raise B2TRADERExecutionError(
                "Live order blocked: set B2TRADER_LIVE_TRADING=true explicitly"
            )
        if not self.account_id:
            raise B2TRADERExecutionError("B2TRADER_ACCOUNT_ID is required")
        return self._request(
            "POST",
            "/frontoffice/api/cfd/v4/orders",
            {"order": order},
        )

    def cancel_order(self, order_id):
        if not self.live_enabled:
            raise B2TRADERExecutionError("Live order blocked")
        return self._request(
            "DELETE",
            f"/frontoffice/api/v3/orders/{order_id}",
        )
