from __future__ import annotations

import pandas as pd

from backtest.crt_tbs_14d import body_tbs_candidates, htf_purges


def bars(rows):
    index = pd.date_range("2026-01-01", periods=len(rows), freq="5min", tz="UTC")
    return pd.DataFrame(rows, index=index, columns=["open", "high", "low", "close"])


def test_body_close_tbs_requires_reentry_and_accepts_gap_two_to_six():
    frame = bars([
        (100, 100.5, 99.5, 100), (100, 100.6, 99.4, 100),
        (100, 101, 99, 100), (100, 101.1, 99.2, 100.1),
        (100.1, 100.8, 99.3, 100), (100, 100.9, 99.4, 100.1),
        (100.1, 101.2, 99.8, 100.8), (100.8, 102.0, 99.8, 101.5),  # body close beyond level
        (101.5, 101.6, 99.0, 100.0), # re-entry confirmation
        (100, 100.5, 99.5, 100),
    ])
    candidates = body_tbs_candidates(frame, 0, len(frame), "SHORT")
    assert candidates
    assert candidates[0]["entry"] == 8
    assert 2 <= candidates[0]["gap"] <= 6


def test_htf_purge_requires_close_back_inside_previous_range():
    index = pd.date_range("2026-01-01", periods=3, freq="2h", tz="UTC")
    htf = pd.DataFrame([
        (100, 105, 95, 100),
        (100, 106, 96, 104),  # sweeps high but closes back inside 105
        (104, 105, 97, 100),
    ], index=index, columns=["open", "high", "low", "close"])
    purges = htf_purges(pd.DataFrame(), htf)
    assert len(purges) == 1
    row = next(iter(purges.values()))
    assert row["side"] == "SHORT"
    assert row["range_high"] == 105


def test_htf_purge_rejects_close_outside_range():
    index = pd.date_range("2026-01-01", periods=3, freq="2h", tz="UTC")
    htf = pd.DataFrame([
        (100, 105, 95, 100),
        (100, 106, 96, 105.5),
        (105.5, 107, 97, 100),
    ], index=index, columns=["open", "high", "low", "close"])
    assert htf_purges(pd.DataFrame(), htf) == {}
