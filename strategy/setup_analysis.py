"""Setup analysis and hard validation for the private SMC/ICT strategy.

There is deliberately no arbitrary confidence score. Hard requirements are
boolean gates; Fib/session/OB are evidence and diagnostics rather than
independent triggers.
"""

def analyze_setup(*, htf, sweep, mss, displacement_ok, fvg, ob=None,
                  fib=None, session=None, rr=None):
    evidence = {
        "htf_structure": htf.get("structure") if htf else None,
        "premium_discount": htf.get("premium_discount") if htf else None,
        "sweep": bool(sweep),
        "mss": bool(mss),
        "displacement": bool(displacement_ok),
        "fvg": bool(fvg),
        "order_block": bool(ob),
        "fib_cluster": bool(fib and fib.get("best")),
        "session": session,
        "rr": rr,
    }
    return evidence


def validate_setup(*, bias, htf, sweep, mss, displacement_ok, fvg,
                   session, rr, min_rr=2.0, require_sweep=True,
                   require_mss=True, require_displacement=True,
                   require_fvg=True, require_session=True,
                   require_premium_discount=True, require_min_rr=True):
    reasons = []
    if bias not in ("LONG", "SHORT"):
        reasons.append("NO_DIRECTIONAL_BIAS")
    if not htf or htf.get("bias") != bias:
        reasons.append("HTF_STRUCTURE_MISMATCH")
    if require_sweep and not sweep:
        reasons.append("NO_VALID_LIQUIDITY_SWEEP")
    if require_mss and not mss:
        reasons.append("NO_POST_SWEEP_MSS")
    if require_displacement and not displacement_ok:
        reasons.append("NO_DISPLACEMENT")
    if require_fvg and not fvg:
        reasons.append("NO_VALID_FVG")
    if require_session and session not in ("london", "new_york", "overlap"):
        reasons.append("OUTSIDE_TRADE_SESSION")
    if require_min_rr and (rr is None or rr < min_rr):
        reasons.append("INSUFFICIENT_RR")
    if require_premium_discount and bias == "LONG" and (not htf or htf.get("premium_discount") != "DISCOUNT"):
        reasons.append("LONG_NOT_IN_DISCOUNT")
    if require_premium_discount and bias == "SHORT" and (not htf or htf.get("premium_discount") != "PREMIUM"):
        reasons.append("SHORT_NOT_IN_PREMIUM")
    return {"valid": not reasons, "reasons": reasons}
