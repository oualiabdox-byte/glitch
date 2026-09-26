from strategy.variants import VARIANTS, available_variants, build_variant


def test_requested_variants_are_registered():
    assert set(available_variants()) == {
        "eurusd_swing3_choch_or_bos",
        "gbpusd_swing2_choch_only",
        "eurusd_swing2_choch_or_bos",
    }
    assert VARIANTS["eurusd_swing3_choch_or_bos"]["swing_length"] == 3
    assert VARIANTS["gbpusd_swing2_choch_only"]["m5_confirmation_mode"] == "CHOCH_ONLY"
    assert VARIANTS["eurusd_swing2_choch_or_bos"]["swing_length"] == 2


def test_requested_variants_build_causal_strategies():
    for name in available_variants():
        strategy = build_variant(name)
        assert strategy.swing_left == strategy.swing_right
        assert strategy.min_rr == 0.0
        assert strategy.stop_buffer == 0.0
