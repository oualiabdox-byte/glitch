import pytest

from execution.demo_guard import DEMO_CONFIRMATION, require_demo_execution


def set_valid_demo_env(monkeypatch):
    monkeypatch.setenv("CTRADER_ENV", "demo")
    monkeypatch.setenv("CTRADER_ALLOW_ORDERS", "true")
    monkeypatch.setenv("CTRADER_DEMO_CONFIRM", DEMO_CONFIRMATION)
    monkeypatch.setenv("CTRADER_MAX_ORDER_VOLUME_UNITS", "1000")


def test_demo_gate_requires_explicit_confirmation(monkeypatch):
    set_valid_demo_env(monkeypatch)
    monkeypatch.setenv("CTRADER_DEMO_CONFIRM", "")
    with pytest.raises(RuntimeError, match="CTRADER_DEMO_CONFIRM"):
        require_demo_execution()


def test_demo_gate_rejects_live_environment(monkeypatch):
    set_valid_demo_env(monkeypatch)
    monkeypatch.setenv("CTRADER_ENV", "live")
    with pytest.raises(RuntimeError, match="demo"):
        require_demo_execution()


def test_demo_gate_accepts_only_complete_demo_configuration(monkeypatch):
    set_valid_demo_env(monkeypatch)
    require_demo_execution()


def test_demo_gate_requires_positive_volume_cap(monkeypatch):
    set_valid_demo_env(monkeypatch)
    monkeypatch.setenv("CTRADER_MAX_ORDER_VOLUME_UNITS", "0")
    with pytest.raises(RuntimeError, match="volume cap"):
        require_demo_execution()


def test_live_configuration_is_rejected_by_adapter(monkeypatch):
    monkeypatch.setenv("CTRADER_ENV", "live")
    monkeypatch.setenv("CTRADER_CLIENT_ID", "x")
    monkeypatch.setenv("CTRADER_CLIENT_SECRET", "x")
    monkeypatch.setenv("CTRADER_ACCESS_TOKEN", "x")
    from execution.ctrader_adapter import CTraderConfig

    with pytest.raises(RuntimeError, match="Live routing is disabled"):
        CTraderConfig.from_env()
