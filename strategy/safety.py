"""Optional execution-quality and market-condition safety helpers.

These helpers are deliberately independent of signal generation. A strategy
setup should already be structurally valid before any of these guards are used.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from statistics import median


def as_utc(value):
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _true_ranges(candles, start=1):
    trs = []
    for i in range(max(1, start), len(candles)):
        h, l = candles[i]["high"], candles[i]["low"]
        prev_close = candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - prev_close), abs(l - prev_close)))
    return trs


def volatility_ratio(candles, lookback=20):
    """Current true range relative to the median prior true range."""
    if len(candles) < lookback + 2:
        return None
    trs = _true_ranges(candles)
    prior = trs[-(lookback + 1):-1]
    current = trs[-1]
    baseline = median(prior) if prior else 0.0
    return current / baseline if baseline > 0 else None


def abnormal_volatility(candles, max_ratio=2.5, lookback=20):
    ratio = volatility_ratio(candles, lookback)
    if ratio is None or max_ratio <= 0:
        return False
    return ratio > max_ratio


def spread_allowed(spread_pips, max_spread_pips=3.0):
    """Return False when a measured live spread is above the configured cap."""
    if spread_pips is None or max_spread_pips <= 0:
        return True
    return float(spread_pips) <= float(max_spread_pips)


def signal_once_per_bar(last_signal_time, current_signal_time):
    if last_signal_time is None:
        return True
    return as_utc(last_signal_time) != as_utc(current_signal_time)


def _pair_currencies(pair):
    clean = "".join(ch for ch in str(pair).upper() if ch.isalpha())
    return {clean[:3], clean[3:]} if len(clean) == 6 else set()


def news_blocked(timestamp, pair, events, pause_before_minutes=45, pause_after_minutes=20):
    """Block only events that affect the pair's currencies.

    Each event may be a timestamp string or a dict containing time_utc and
    optional currencies such as ["USD"]. No static calendar dates are baked
    into the strategy.
    """
    if not events:
        return False
    now = as_utc(timestamp)
    pair_ccy = _pair_currencies(pair)

    for event in events:
        if isinstance(event, str):
            event_time = as_utc(event)
            currencies = set()
        else:
            event_time = as_utc(event["time_utc"])
            currencies = {str(c).upper() for c in event.get("currencies", [])}
        if currencies and not pair_ccy.intersection(currencies):
            continue
        seconds = (event_time - now).total_seconds()
        if -pause_after_minutes * 60 <= seconds <= pause_before_minutes * 60:
            return True
    return False


def load_news_events(raw_json):
    if not raw_json:
        return []
    parsed = json.loads(raw_json)
    if not isinstance(parsed, list):
        raise ValueError("news events JSON must be a list")
    return parsed


def volume_context(candles, lookback=20):
    """Non-authoritative relative tick-volume context."""
    volumes = [
        float(c.get("volume", c.get("tick_volume", 0)))
        for c in candles[-(lookback + 1):]
    ]
    if len(volumes) < 2:
        return {"available": False}
    baseline = median(volumes[:-1])
    current = volumes[-1]
    return {
        "available": baseline > 0,
        "current": current,
        "median_prior": baseline,
        "ratio": current / baseline if baseline > 0 else None,
    }
