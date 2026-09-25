from backtest.data_quality import validate_dataset, validate_ohlc


def bar(time, open_=1.0, high=1.1, low=0.9, close=1.05):
    return {"time": time, "open": open_, "high": high, "low": low, "close": close}


def test_quality_accepts_monotonic_aligned_data():
    h1 = [bar("2025-01-01T00:00:00+00:00"), bar("2025-01-01T01:00:00+00:00")]
    m5 = [bar("2025-01-01T00:00:00+00:00"), bar("2025-01-01T00:05:00+00:00")]
    report = validate_dataset(h1, m5)
    assert report["valid"] is True


def test_quality_rejects_duplicate_and_bad_ohlc():
    bars = [bar("2025-01-01T00:00:00+00:00", high=0.8), bar("2025-01-01T00:00:00+00:00")]
    report = validate_ohlc(bars, 60, "h1")
    assert report["valid"] is False
    assert any("DUPLICATE" in reason for reason in report["errors"])
    assert any("OHLC_INCONSISTENT" in reason for reason in report["errors"])


def test_quality_rejects_unaligned_m5():
    report = validate_dataset(
        [bar("2025-01-01T00:00:00+00:00")],
        [bar("2025-01-01T00:00:00+00:00"), bar("2025-01-01T00:10:00+00:00")],
    )
    assert report["valid"] is False
    assert any("INVALID_INTERVAL" in reason for reason in report["errors"])
