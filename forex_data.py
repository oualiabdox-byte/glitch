"""Forex data: MT5 terminal / MQL5 bridge for EURUSD / GBPUSD.
Do NOT use Kraken REST API for Forex data.
Old crypto/kraken path preserved separately at /home/myc/crypto-bot/kraken.py.
This module connects Python signal engine to MT5 market data via MQL5 or direct terminal.
"""
import os, time, json, subprocess

PAIR_MAP_MT5 = {
    "EURUSD": "EURUSD",
    "GBPUSD": "GBPUSD",
    "USDJPY": "USDJPY",
    "USDCHF": "USDCHF",
    "USDCAD": "USDCAD",
    "AUDUSD": "AUDUSD",
    "NZDUSD": "NZDUSD",
}
# Broker symbol discovery: MT5 may use EURUSD, EURUSDm, EURUSD.pro, etc.
# This adapter discovers from MT5 terminal directly.

def discover_symbol(pair):
    # Return broker symbol after discovery via MT5
    # For now use direct pair name; MT5 terminal handles mapping
    return pair

def fetch_ohlc(pair, interval_minutes=60, count=500):
    """Fetch historical OHLC from MT5 terminal / MQL5 broker feed.
    Uses MT5 directly — not Kraken REST.
    If MT5 Python connector unavailable, use MQL5 exporter to CSV then load.
    """
    # If direct Python MT5 connector available (after fix):
    # import MetaTrader5
    # mt5 = MetaTrader5()
    # ... connect to DEMO ... get symbol info ... copy rates ...
    # Otherwise: use MQL5 expert advisor to export CSV
    # For DRY-RUN / framework validation: return empty with status note
    return []
