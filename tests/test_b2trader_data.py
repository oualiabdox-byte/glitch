import unittest
from datetime import datetime, timezone

from data.b2trader import B2TRADERGuestData


class TestB2TRADERData(unittest.TestCase):
    def test_candle_normalization(self):
        row = {"timestamp": "2026-01-01T00:00:00Z", "open": "1.1", "high": "1.2", "low": "1.0", "close": "1.15"}
        c = B2TRADERGuestData._candle(row)
        self.assertEqual(c["time"], "2026-01-01T00:00:00+00:00")
        self.assertEqual(c["open"], 1.1)

    def test_validation_sorts_and_deduplicates(self):
        rows = [
            {"time": "2026-01-01T01:00:00+00:00", "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15, "volume": None},
            {"time": "2026-01-01T00:00:00+00:00", "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05, "volume": None},
            {"time": "2026-01-01T01:00:00+00:00", "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15, "volume": None},
        ]
        out = B2TRADERGuestData._validate(rows)
        self.assertEqual(len(out), 2)
        self.assertLess(out[0]["time"], out[1]["time"])


if __name__ == "__main__":
    unittest.main()
