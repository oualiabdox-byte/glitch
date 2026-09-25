from __future__ import annotations

from datetime import datetime, timedelta, timezone

import execution.bot_main as bot_main
from config.settings import load_config, risk_config


def _row(opened: datetime) -> dict:
    return {
        "time": opened.isoformat(),
        "open": 1.0,
        "high": 1.01,
        "low": 0.99,
        "close": 1.0,
    }


def test_yaml_quote_age_is_used_and_can_be_overridden():
    config = load_config()
    assert risk_config(config, {})["max_quote_age_seconds"] == 60
    assert risk_config(config, {"CTRADER_MAX_QUOTE_AGE_SECONDS": "90"})[
        "max_quote_age_seconds"
    ] == 90


def test_quote_age_override_must_remain_positive():
    import pytest

    with pytest.raises(ValueError, match="max_quote_age_seconds must be >= 1"):
        risk_config(load_config(), {"CTRADER_MAX_QUOTE_AGE_SECONDS": "0"})


def test_latest_scheduled_closed_h1_and_m5_bars_are_fresh_within_period():
    now = datetime(2026, 9, 25, 10, 30, tzinfo=timezone.utc)
    h1 = [_row(now.replace(minute=0) - timedelta(hours=i + 1)) for i in range(20)]
    m5 = [_row(now.replace(minute=25) - timedelta(minutes=5 * i)) for i in range(20)]
    result = bot_main._freshness_check(h1, m5, now, max_quote_age_seconds=60)
    assert result["fresh"] is True
    assert result["reason_codes"] == []
    assert result["frames"]["h1"]["latest_close_utc"] == "2026-09-25T10:00:00+00:00"
    assert result["frames"]["m5"]["latest_close_utc"] == "2026-09-25T10:30:00+00:00"


def test_stale_h1_and_m5_are_rejected_after_close_grace():
    now = datetime(2026, 9, 25, 11, 6, 1, tzinfo=timezone.utc)
    h1 = [_row(now.replace(hour=9, minute=0, second=0) - timedelta(hours=i)) for i in range(20)]
    m5 = [_row(now.replace(hour=10, minute=55, second=0) - timedelta(minutes=5 * i))
          for i in range(20)]
    result = bot_main._freshness_check(h1, m5, now, max_quote_age_seconds=60)
    assert result["fresh"] is False
    assert set(result["reason_codes"]) == {"STALE_H1_DATA", "STALE_M5_DATA"}


def test_stale_h1_is_reported_while_m5_remains_fresh():
    now = datetime(2026, 9, 25, 11, 1, 1, tzinfo=timezone.utc)
    h1 = [_row(datetime(2026, 9, 25, 9, tzinfo=timezone.utc)
               - timedelta(hours=i)) for i in range(20)]
    m5 = [_row(datetime(2026, 9, 25, 10, 55, tzinfo=timezone.utc)
               - timedelta(minutes=5 * i)) for i in range(20)]
    result = bot_main._freshness_check(h1, m5, now, max_quote_age_seconds=60)
    assert result["reason_codes"] == ["STALE_H1_DATA"]


def test_stale_m5_is_reported_while_h1_remains_fresh():
    now = datetime(2026, 9, 25, 11, 6, 1, tzinfo=timezone.utc)
    h1 = [_row(datetime(2026, 9, 25, 10, tzinfo=timezone.utc)
               - timedelta(hours=i)) for i in range(20)]
    m5 = [_row(datetime(2026, 9, 25, 10, 55, tzinfo=timezone.utc)
               - timedelta(minutes=5 * i)) for i in range(20)]
    result = bot_main._freshness_check(h1, m5, now, max_quote_age_seconds=60)
    assert result["reason_codes"] == ["STALE_M5_DATA"]


def test_scan_returns_stale_data_reason_before_running_strategy(monkeypatch):
    now = datetime(2026, 9, 25, 10, 6, 1, tzinfo=timezone.utc)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz) if tz else now.replace(tzinfo=None)

    class FakeFeed:
        def download(self, pair, start, end, periods):
            h1 = sorted((_row(datetime(2026, 9, 25, 10, tzinfo=timezone.utc)
                              - timedelta(hours=i + 1)) for i in range(24)),
                        key=lambda row: row["time"])
            # The latest M5 bar closes at 10:00; 10:05 has closed and the
            # configured one-minute grace period has elapsed.
            m5 = sorted((_row(datetime(2026, 9, 25, 9, 55, tzinfo=timezone.utc)
                              - timedelta(minutes=5 * i)) for i in range(30)),
                        key=lambda row: row["time"])
            return {"h1": h1, "m5": m5}

    monkeypatch.setattr(bot_main, "datetime", FrozenDateTime)
    monkeypatch.setattr(bot_main, "load_config", lambda: {"risk": {"max_quote_age_seconds": 60}})
    monkeypatch.setattr(bot_main, "CTraderData", FakeFeed)
    monkeypatch.setattr(bot_main.safety, "abnormal_volatility",
                        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("stale data reached strategy safety checks")))
    result = bot_main.scan("EURUSD")
    assert result["status"] == "NO_TRADE"
    assert result["reason_codes"] == ["STALE_M5_DATA"]
    assert result["data_freshness"]["fresh"] is False
