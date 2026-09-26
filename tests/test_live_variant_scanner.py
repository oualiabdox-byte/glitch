from __future__ import annotations

import json
import sys
from types import SimpleNamespace

from execution import bot_main
from strategy.variants import VARIANTS, build_variant, variants_for_pair


def test_pair_lookup_selects_every_matching_preset():
    assert variants_for_pair("EURUSD") == (
        "eurusd_swing3_choch_or_bos",
        "eurusd_swing2_choch_or_bos",
    )
    assert variants_for_pair("GBP/USD") == ("gbpusd_swing2_choch_only",)
    assert variants_for_pair("USDJPY") == ()


def test_named_presets_override_strategy_sensitivity_and_confirmation():
    for name, spec in VARIANTS.items():
        strategy = build_variant(name)
        assert strategy.swing_left == spec["swing_length"]
        assert strategy.swing_right == spec["swing_length"]
        assert strategy.m5_confirmation_mode == spec["m5_confirmation_mode"]


def test_presets_keep_other_runtime_strategy_options():
    strategy = build_variant("gbpusd_swing2_choch_only", {
        "swing_length": 3,
        "setup_max_age_hours": 24,
        "allow_weak_structure": False,
        "m5_confirmation_mode": "CHOCH_OR_BOS",
    })
    assert strategy.swing_left == strategy.swing_right == 2
    assert strategy.setup_max_age_hours == 24
    assert strategy.allow_weak_structure is False
    assert strategy.m5_confirmation_mode == "CHOCH_ONLY"


def test_cli_scans_all_three_presets_and_uses_config_default_for_other_pairs(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["bot_main"])
    monkeypatch.setenv("CTRADER_PAIRS", "EURUSD,GBPUSD,USDJPY")
    monkeypatch.setattr(bot_main, "load_config", lambda: {})
    calls = []

    def fake_scan(pair, setup_state=None, variant_name=None):
        calls.append((pair, variant_name, setup_state))
        return {"pair": pair, "variant": variant_name, "status": "NO_TRADE"}

    monkeypatch.setattr(bot_main, "scan", fake_scan)
    bot_main.main()

    assert [(pair, variant) for pair, variant, _ in calls] == [
        ("EURUSD", "eurusd_swing3_choch_or_bos"),
        ("EURUSD", "eurusd_swing2_choch_or_bos"),
        ("GBPUSD", "gbpusd_swing2_choch_only"),
        ("USDJPY", "config_default"),
    ]
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()
              if line.startswith("{")]
    assert [row["variant"] for row in output] == [variant for _, variant, _ in calls]


def test_scan_instantiates_the_requested_variant(monkeypatch):
    from datetime import datetime, timezone, timedelta

    frozen_now = datetime(2026, 9, 26, 11, 30, tzinfo=timezone.utc)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return frozen_now if tz else frozen_now.replace(tzinfo=None)

    def candle(opened):
        return {"time": opened.isoformat(), "open": 1.0, "high": 1.01,
                "low": 0.99, "close": 1.0}

    class FakeFeed:
        def download(self, pair, start, end, periods):
            h1 = [candle(frozen_now.replace(minute=0) - timedelta(hours=i + 1))
                  for i in reversed(range(24))]
            m5 = [candle(frozen_now - timedelta(minutes=5 * (i + 1)))
                  for i in reversed(range(30))]
            return {"h1": h1, "m5": m5}

    selected = []

    class FakeStrategy:
        def evaluate(self, h1, m5, setup_state=None):
            return SimpleNamespace(status="NO_TRADE", reason_codes=["TEST_NO_SIGNAL"],
                                   evidence={}, is_signal=False)

    def fake_build_variant(name, base_options=None):
        selected.append((name, base_options))
        return FakeStrategy()

    monkeypatch.setattr(bot_main, "datetime", FrozenDateTime)
    monkeypatch.setattr(bot_main, "load_config", lambda: {
        "risk": {"max_quote_age_seconds": 60},
        "strategy": {"swing_length": 3, "setup_max_age_hours": 72},
    })
    monkeypatch.setattr(bot_main, "CTraderData", FakeFeed)
    monkeypatch.setattr(bot_main, "build_variant", fake_build_variant)
    monkeypatch.setattr(bot_main.safety, "abnormal_volatility", lambda *args, **kwargs: False)
    monkeypatch.setattr(bot_main.safety, "news_blocked", lambda *args, **kwargs: False)

    result = bot_main.scan("EURUSD", variant_name="eurusd_swing3_choch_or_bos")
    assert result["variant"] == "eurusd_swing3_choch_or_bos"
    assert result["status"] == "NO_TRADE"
    assert selected[0][0] == "eurusd_swing3_choch_or_bos"


def test_repeated_runner_collects_every_variant_result(monkeypatch):
    from execution import demo_runner

    rows = [
        {"pair": "EURUSD", "variant": name, "status": "NO_TRADE"}
        for name in variants_for_pair("EURUSD")
    ]
    called = {}

    def fake_run(command, **kwargs):
        called.update(kwargs)
        return SimpleNamespace(returncode=0,
                               stdout="\n".join(json.dumps(row) for row in rows),
                               stderr="")

    monkeypatch.setattr(demo_runner.subprocess, "run", fake_run)
    results = demo_runner._scan("EURUSD", setup_states={
        "eurusd_swing3_choch_or_bos": {"status": "WAITING_FOR_POI_TOUCH"},
    })

    assert [row["variant"] for row in results] == list(variants_for_pair("EURUSD"))
    assert json.loads(called["env"]["CTRADER_SETUP_STATE_JSON"])[
        "eurusd_swing3_choch_or_bos"]["status"] == "WAITING_FOR_POI_TOUCH"
