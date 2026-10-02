from __future__ import annotations

import pandas as pd

from strategy.crt_trader import CrtTbsTrader


def test_crt_trader_declares_installed_m15_policy():
    report = CrtTbsTrader().report()
    assert report["engine"] == "CRT_M15_4H_FILTERED"
    assert report["htf_rule"] == "2h"
    assert report["execution_timeframe"] == "15m"
    assert report["post_purge_window_hours"] == 4
    assert report["min_entry_body_ratio"] == 0.5
    assert report["min_stop_distance_atr"] == 0.75


def test_crt_trader_empty_frame_has_no_signals():
    frame = pd.DataFrame(columns=["open", "high", "low", "close", "volume"],
                         index=pd.DatetimeIndex([], tz="UTC"))
    assert CrtTbsTrader().signals(frame, "EURUSD") == []
