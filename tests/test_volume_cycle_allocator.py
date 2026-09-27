from strategy.volume_cycle_allocator import (
    AdaptiveAllocator,
    AllocatorConfig,
    VolumeCycle,
    build_volume_cycles,
    validate_volume_bars,
)


def bars(count=40, volume=10.0):
    result = []
    for i in range(count):
        close = 1.0 + i * 0.001
        result.append({
            "time": f"2026-01-01T00:{i:02d}:00+00:00",
            "open": close,
            "high": close + 0.001,
            "low": close - 0.001,
            "close": close,
            "volume": volume,
        })
    return result


def test_volume_validation_requires_positive_native_volume():
    data = bars(3)
    data[1]["volume"] = 0
    report = validate_volume_bars(data, "EURUSD")
    assert report["valid"] is False
    assert any("NON_POSITIVE_VOLUME" in error for error in report["errors"])


def test_cycles_use_prior_volume_quota_and_exclude_incomplete_tail():
    data = bars(30, volume=10)
    config = AllocatorConfig(target_cycle_bars=4, volume_lookback_bars=4, warmup_bars=4)
    cycles = build_volume_cycles("EURUSD", data, config)
    assert cycles
    assert cycles[0].target_volume == 40
    assert cycles[0].bars == 4
    assert cycles[-1].end_index < len(data)


def test_allocator_starts_equal_and_caps_adaptive_weights():
    config = AllocatorConfig(max_weight=0.4)
    allocator = AdaptiveAllocator(["EURUSD", "GBPUSD", "USDJPY"], config)
    initial = allocator.weights()
    assert initial == {"EURUSD": 1 / 3, "GBPUSD": 1 / 3, "USDJPY": 1 / 3}
    allocator.record_completed_cycle(VolumeCycle("EURUSD", 0, "a", "b", 0, 1, 2, 20, 20, 0.02))
    allocator.record_completed_cycle(VolumeCycle("EURUSD", 1, "b", "c", 2, 3, 2, 20, 20, 0.02))
    weights = allocator.weights()
    assert abs(sum(weights.values()) - 1.0) < 1e-12
    assert max(weights.values()) <= 0.4 + 1e-12
    assert weights["EURUSD"] >= weights["GBPUSD"]


def test_negative_cycle_does_not_receive_positive_momentum_bonus():
    allocator = AdaptiveAllocator(["EURUSD", "GBPUSD"])
    allocator.record_completed_cycle(VolumeCycle("EURUSD", 0, "a", "b", 0, 1, 2, 20, 20, -0.02))
    weights = allocator.weights()
    assert weights["EURUSD"] == weights["GBPUSD"]
