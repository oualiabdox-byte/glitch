from __future__ import annotations

import pandas as pd

from strategy.crt_trader import CrtTbsTrader


def test_crt_trader_declares_research_only_policy():
    report = CrtTbsTrader().report()
    assert report["htf_rule"] == "2h"
    assert report["entry_rule"] == "body_close_reentry"
    assert report["execution"] == "research_only_no_orders"


def test_crt_trader_empty_frame_has_no_signals():
    frame = pd.DataFrame(columns=["open", "high", "low", "close", "volume"],
                         index=pd.DatetimeIndex([], tz="UTC"))
    assert CrtTbsTrader().signals(frame, "EURUSD") == []
