import json
from pathlib import Path

import pytest

from strategy.auction_mean_reversion import backtest_pair
from strategy.auction_mean_reversion_v2 import (
    DEFAULT_MAX_EFFICIENCY_RATIO,
    backtest_pair_v2,
    efficiency_ratio,
)

ROOT = Path(__file__).resolve().parents[1]


def _rows_from_closes(closes):
    return [
        {"time": str(i), "open": close, "high": close, "low": close, "close": close}
        for i, close in enumerate(closes)
    ]


def test_efficiency_ratio_is_one_for_monotonic_path():
    rows = _rows_from_closes([100, 101, 102, 103, 104])
    assert efficiency_ratio(rows, end_index=4, lookback=4) == pytest.approx(1.0)


def test_efficiency_ratio_is_low_for_choppy_path_and_uses_no_future_rows():
    closes = [100, 102, 100, 102, 101]
    rows = _rows_from_closes(closes)
    er = efficiency_ratio(rows, end_index=4, lookback=4)
    assert er == pytest.approx(1 / 7)
    extended = rows + _rows_from_closes([250, 251])
    assert efficiency_ratio(extended, end_index=4, lookback=4) == er


def test_v2_default_threshold_is_preregistered_value():
    assert DEFAULT_MAX_EFFICIENCY_RATIO == 0.30


def test_disabling_gate_reproduces_frozen_b1_on_real_14d_data():
    source = ROOT / "backtest" / "ctrader_volume_data" / "EURUSD_m5_14d.json"
    rows = json.loads(source.read_text(encoding="utf-8"))["candles"]
    b1 = backtest_pair("EURUSD", rows)
    v2_without_gate, _ = backtest_pair_v2(
        "EURUSD", rows, max_efficiency_ratio=None
    )
    assert v2_without_gate == b1


def test_filter_threshold_must_be_in_range():
    with pytest.raises(ValueError):
        backtest_pair_v2("EURUSD", [], max_efficiency_ratio=1.01)
