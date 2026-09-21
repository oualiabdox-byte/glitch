import unittest

from strategy.dominating_candle import (
    find_dominating_candle,
    dc_breakout,
)


class TestDominatingCandle(unittest.TestCase):
    def _c(self, t, o, h, l, close):
        return {
            "time": f"2026-01-01T{t:02d}:00:00+00:00",
            "open": o,
            "high": h,
            "low": l,
            "close": close,
        }

    def test_full_range_contains_three_newer_bodies(self):
        candles = [
            self._c(0, 1.00, 1.20, 0.80, 1.10),
            self._c(1, 0.98, 1.16, 0.90, 1.08),
            self._c(2, 1.06, 1.18, 0.92, 1.12),
            self._c(3, 1.10, 1.19, 0.95, 1.15),
        ]
        dc = find_dominating_candle(candles, min_contained=3, lookback=8)
        self.assertIsNotNone(dc)
        self.assertEqual(dc["index"], 0)
        self.assertEqual(dc["contained_bars"], 3)

    def test_body_outside_full_range_invalidates_dc(self):
        candles = [
            self._c(0, 1.00, 1.20, 0.80, 1.10),
            self._c(1, 0.98, 1.16, 0.90, 1.08),
            self._c(2, 1.06, 1.18, 0.92, 1.12),
            self._c(3, 1.10, 1.30, 0.95, 1.25),
        ]
        self.assertIsNone(find_dominating_candle(candles, min_contained=3, lookback=8))

    def test_close_outside_dc_is_breakout(self):
        dc = {"low": 0.80, "high": 1.20}
        candles = [self._c(0, 1.10, 1.25, 1.00, 1.23)]
        self.assertEqual(dc_breakout(candles, dc), "LONG")


if __name__ == "__main__":
    unittest.main()
