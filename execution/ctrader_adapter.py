"""cTrader Open API adapter.

Broker/execution layer only. Strategy decisions stay in strategy/.
Credentials are supplied via environment/OpenClaw secrets; never commit them.

The adapter starts in read-only mode. Live order submission is intentionally
not implemented until cTrader application approval, account authorization,
and Demo integration tests are complete.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CTraderConfig:
    client_id: str
    client_secret: str
    environment: str = "demo"

    @classmethod
    def from_env(cls) -> "CTraderConfig":
        client_id = os.getenv("CTRADER_CLIENT_ID", "").strip()
        client_secret = os.getenv("CTRADER_CLIENT_SECRET", "").strip()
        environment = os.getenv("CTRADER_ENV", "demo").strip().lower()
        if not client_id:
            raise RuntimeError("CTRADER_CLIENT_ID is required")
        if not client_secret:
            raise RuntimeError("CTRADER_CLIENT_SECRET is required")
        if environment not in {"demo", "live"}:
            raise RuntimeError("CTRADER_ENV must be demo or live")
        return cls(client_id, client_secret, environment)


class CTraderAdapter:
    """Thin cTrader connection/configuration layer.

    This class deliberately does not contain BUY/SELL logic.
    """

    def __init__(self, config: Optional[CTraderConfig] = None):
        self.config = config or CTraderConfig.from_env()

    @property
    def host(self) -> str:
        return (
            "demo.ctraderapi.com"
            if self.config.environment == "demo"
            else "live.ctraderapi.com"
        )

    @property
    def port(self) -> int:
        return 5035

    def describe(self) -> dict:
        return {
            "broker": "cTrader",
            "environment": self.config.environment,
            "host": self.host,
            "port": self.port,
            "order_submission": False,
        }
