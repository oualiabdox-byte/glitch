import pytest

from strategy import smc_engine


def test_pyvsmc_api_surface_is_supported_when_installed():
    if smc_engine._pyvsmc is None:
        pytest.skip("pyvsmc is not installed in this test environment")
    required = (
        "detect_fvg",
        "detect_structure",
        "detect_liquidity",
        "detect_zones",
        "detect_order_blocks",
    )
    assert all(callable(getattr(smc_engine._pyvsmc, name, None)) for name in required)


def test_smc_engine_is_descriptive_and_does_not_require_full_stack():
    candles = []
    for i in range(40):
        base = 1.1000 + i * 0.0001
        candles.append({
            "open": base,
            "high": base + 0.0005,
            "low": base - 0.0005,
            "close": base + 0.0002,
            "time": str(i),
        })

    result = smc_engine.analyze(candles)
    assert "available" in result
    assert result["engine"] in ("pyvsmc", "local")
