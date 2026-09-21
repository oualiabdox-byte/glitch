from strategy.fvg import find_fvg


def candle(o, h, l, c, t):
    return {"open": o, "high": h, "low": l, "close": c, "time": t}


def test_fvg_does_not_use_current_unclosed_candle():
    bars = [
        candle(1.1000, 1.1010, 1.0990, 1.1005, "0"),
        candle(1.1005, 1.1040, 1.1000, 1.1035, "1"),
        candle(1.1035, 1.1060, 1.1050, 1.1055, "2"),
        candle(1.1055, 1.1200, 1.0900, 1.1000, "3"),
    ]
    zone = find_fvg(bars, required_side="LONG")
    assert zone is not None
    assert zone["creator_idx"] == 1
    assert zone["creator_idx"] < len(bars) - 1
