"""Auditable strategy decisions; legacy evaluators may still return setup/None."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Decision:
    status: str
    reason_codes: tuple[str, ...] = ()
    signal_time: str | None = None
    data_cutoff_utc: str | None = None
    setup: dict[str, Any] | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def is_signal(self) -> bool:
        return self.status == "SIGNAL" and self.setup is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "signal_time": self.signal_time,
            "data_cutoff_utc": self.data_cutoff_utc,
            "setup": self.setup,
            "evidence": self.evidence,
        }


def signal(setup: dict[str, Any], *, data_cutoff_utc: str, evidence=None) -> Decision:
    return Decision(
        status="SIGNAL",
        signal_time=setup.get("timestamp"),
        data_cutoff_utc=data_cutoff_utc,
        setup=setup,
        evidence=evidence or setup.get("evidence", {}),
    )


def no_trade(*reasons: str, data_cutoff_utc=None, evidence=None) -> Decision:
    unique = tuple(dict.fromkeys(reason for reason in reasons if reason))
    return Decision(
        status="NO_TRADE",
        reason_codes=unique or ("NO_SIGNAL",),
        data_cutoff_utc=data_cutoff_utc,
        evidence=evidence or {},
    )


def evaluate_entry_decision(candles_1h, candles_4h, pair, mode, session_context="london", swing_length=3):
    """Evaluate one entry mode without exposing ``None`` at the boundary."""
    from . import ict_bias, liquidity, breakout_retest
    from .ict_strategy import evaluate_ict_2022, evaluate_breakout_retest, evaluate_structure_entry

    cutoff = candles_1h[-1].get("time") if candles_1h else None
    if len(candles_1h) < 30 or len(candles_4h) < 30:
        return no_trade("INSUFFICIENT_HISTORY", data_cutoff_utc=cutoff)
    htf = ict_bias.htf_context_4h(candles_4h, swing_length=swing_length)
    bias = htf.get("bias")
    evidence = {
        "h4_bias": bias,
        "premium_discount": htf.get("premium_discount"),
        "data_cutoff_utc": cutoff,
        "mode": mode,
    }
    if bias not in ("LONG", "SHORT"):
        return no_trade("HTF_NO_DIRECTIONAL_BIAS", data_cutoff_utc=cutoff, evidence=evidence)
    if session_context not in ("london", "new_york", "overlap") and mode == "ict_fvg":
        return no_trade("SESSION_BLOCK", data_cutoff_utc=cutoff, evidence=evidence)

    if mode == "breakout_retest":
        raw = breakout_retest.find_breakout_retest(
            candles_1h, bias, end_idx=len(candles_1h) - 1,
            swing_length=swing_length,
        )
        if not raw:
            return no_trade("BREAKOUT_RETEST_NOT_CONFIRMED", data_cutoff_utc=cutoff, evidence=evidence)
        evidence.update({"breakout_idx": raw["breakout_idx"], "retest_idx": raw["retest_idx"]})
        evaluator = evaluate_breakout_retest
    elif mode == "structure_entry":
        evaluator = evaluate_structure_entry
    elif mode == "ict_fvg":
        evaluator = evaluate_ict_2022
    else:
        return no_trade("UNKNOWN_ENTRY_MODE", data_cutoff_utc=cutoff, evidence=evidence)

    setup = evaluator(
        candles_1h, candles_4h, pair,
        session_context=session_context,
        swing_length=swing_length,
    )
    if setup is None:
        code = {
            "ict_fvg": "ICT_FVG_GATE_REJECTED",
            "breakout_retest": "BREAKOUT_TARGET_OR_RR_REJECTED",
            "structure_entry": "STRUCTURE_GATE_REJECTED",
        }[mode]
        return no_trade(code, data_cutoff_utc=cutoff, evidence=evidence)
    return signal(setup, data_cutoff_utc=cutoff, evidence=setup.get("evidence", evidence))
