from strategy.setup_analysis import analyze_setup, validate_setup


def test_validator_has_no_score_and_requires_hard_gates():
    htf = {"bias": "LONG", "structure": "BULLISH", "premium_discount": "DISCOUNT"}
    result = validate_setup(
        bias="LONG", htf=htf, sweep={"x": 1}, mss=1,
        displacement_ok=True, fvg={"x": 1}, session="london", rr=2.0,
    )
    assert result["valid"] is True
    assert "score" not in result


def test_validator_rejects_wrong_premium_discount():
    htf = {"bias": "LONG", "structure": "BULLISH", "premium_discount": "PREMIUM"}
    result = validate_setup(
        bias="LONG", htf=htf, sweep={"x": 1}, mss=1,
        displacement_ok=True, fvg={"x": 1}, session="london", rr=3.0,
    )
    assert result["valid"] is False
    assert "LONG_NOT_IN_DISCOUNT" in result["reasons"]


def test_analyzer_reports_confluence_as_evidence_not_score():
    evidence = analyze_setup(
        htf={"structure": "BULLISH", "premium_discount": "DISCOUNT"},
        sweep={"x": 1}, mss=1, displacement_ok=True, fvg={"x": 1},
        ob={"x": 1}, fib={"best": {"count": 2}}, session="london", rr=2.5,
    )
    assert evidence["fib_cluster"] is True
    assert evidence["order_block"] is True
    assert "quality_score" not in evidence


def test_validator_flags_remove_only_selected_gate():
    htf = {"bias": "LONG", "structure": "BULLISH", "premium_discount": "PREMIUM"}
    result = validate_setup(
        bias="LONG", htf=htf, sweep={"x": 1}, mss=1,
        displacement_ok=True, fvg={"x": 1}, session="other", rr=1.0,
        require_session=False, require_premium_discount=False,
        require_min_rr=False,
    )
    assert result["valid"] is True
