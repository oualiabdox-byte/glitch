"""Exness/MetaTrader 5 historical data adapter.

Requires the official MetaTrader5 Python package and a running MT5 terminal
logged into an Exness account. This module only reads market data; it never
places orders.
"""
from datetime import datetime, timezone
from typing import List, Dict

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

TIMEFRAME_MAP = {
    "M5": "TIMEFRAME_M5",
    "H1": "TIMEFRAME_H1",
    "H4": "TIMEFRAME_H4",
}


class ExnessMT5Data:
    def __init__(self, login=None, password=None, server=None, terminal_path=None):
        if mt5 is None:
            raise RuntimeError("MetaTrader5 package is not installed")
        kwargs = {}
        if terminal_path:
            kwargs["path"] = terminal_path
        if login is not None:
            kwargs["login"] = int(login)
        if password:
            kwargs["password"] = password
        if server:
            kwargs["server"] = server
        if not mt5.initialize(**kwargs):
            raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")

    def shutdown(self):
        mt5.shutdown()

    def ensure_symbol(self, symbol):
        info = mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"Exness symbol not found: {symbol}")
        if not info.visible and not mt5.symbol_select(symbol, True):
            raise RuntimeError(f"Could not select symbol: {symbol}")
        return info

    def fetch(self, symbol, timeframe, start, end) -> List[Dict]:
        self.ensure_symbol(symbol)
        tf_name = TIMEFRAME_MAP.get(timeframe.upper())
        if not tf_name or not hasattr(mt5, tf_name):
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        tf = getattr(mt5, tf_name)
        rates = mt5.copy_rates_range(symbol, tf, start, end)
        if rates is None:
            raise RuntimeError(f"copy_rates_range failed for {symbol}: {mt5.last_error()}")

        rows = []
        for r in rates:
            rows.append({
                "time": datetime.fromtimestamp(int(r["time"]), tz=timezone.utc).isoformat(),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": int(r["tick_volume"]),
                "spread_points": int(r["spread"]),
            })
        return rows

    def account_info(self):
        info = mt5.account_info()
        if info is None:
            raise RuntimeError(f"account_info failed: {mt5.last_error()}")
        return {
            "login": info.login,
            "server": info.server,
            "currency": info.currency,
            "balance": float(info.balance),
            "equity": float(info.equity),
            "trade_mode": int(info.trade_mode),
        }
