from __future__ import annotations

from intelligence import hindsight_memory


def test_hindsight_disabled_by_default(monkeypatch):
    monkeypatch.delenv("GLITCH_HINDSIGHT_ENABLED", raising=False)
    assert hindsight_memory.enabled() is False


def test_retain_is_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("GLITCH_HINDSIGHT_ENABLED", raising=False)
    assert hindsight_memory.retain_event("TRADE_OUTCOME", {"pair": "EURUSD"}) is False


def test_event_format_contains_safety_boundary():
    text = hindsight_memory._format_event("ORDER_FILLED", {"pair": "EURUSD"})
    assert "Historical evidence for research only" in text


def test_format_event_is_available():
    assert "EURUSD" in hindsight_memory._format_event("TRADE_OUTCOME", {"pair": "EURUSD"})
