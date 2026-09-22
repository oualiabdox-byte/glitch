from strategy.risk_governor import evaluate_risk


def spec():
    return {"tickSize": 0.0001, "tickValue": 10.0, "lotSize": 100000,
            "minVolume": 1000, "maxVolume": 1000000, "stepVolume": 1000}


def base():
    return dict(
        candidate={"symbol": "EURUSD", "side": "LONG", "entry_price": 1.1000,
                   "stop_price": 1.0980, "risk_amount": 100.0},
        account={"equity": 10000.0, "as_of": "2025-01-01T10:00:00+00:00"},
        open_positions=[], realized_trades=[], symbol_spec=spec(),
        quote={"bid": 1.0999, "ask": 1.1001, "timestamp": "2025-01-01T10:00:00+00:00"},
        limits={"max_spread_pips": 3.0, "max_open_positions": 2,
                "max_daily_loss_r": 3.0, "max_risk_per_trade_r": 0.02,
                "max_quote_age_seconds": 60},
    )


def test_risk_governor_approves_valid_candidate_and_rounds_volume():
    result = evaluate_risk(**base())
    assert result["status"] == "APPROVED"
    assert result["units"] == 50000.0


def test_risk_governor_fails_closed_on_wide_spread():
    args = base()
    args["quote"]["ask"] = 1.1008
    result = evaluate_risk(**args)
    assert result["status"] == "REJECTED"
    assert "SPREAD_LIMIT" in result["reason_codes"]


def test_risk_governor_blocks_open_risk_budget():
    args = base()
    args["open_positions"] = [{"worst_case_risk_r": 3.0}]
    result = evaluate_risk(**args)
    assert result["status"] == "REJECTED"
    assert "DAILY_LOSS_AND_OPEN_RISK_LIMIT" in result["reason_codes"]


def test_risk_governor_rejects_invalid_stop():
    args = base()
    args["candidate"]["stop_price"] = 1.101
    result = evaluate_risk(**args)
    assert result["status"] == "REJECTED"
    assert "INVALID_STOP_DIRECTION" in result["reason_codes"]
