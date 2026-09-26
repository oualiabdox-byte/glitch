"""Deterministic selection of signals emitted by canonical strategy variants.

This module ranks complete strategy outputs only. It does not inspect candles or
create additional trading conditions; the canonical engine remains the sole
source of strategy logic.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .variants import VARIANTS


def _utc_stamp(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def signal_identity(signal: Mapping[str, Any]) -> str:
    """Return a stable identity that distinguishes otherwise identical variants."""
    pair = "".join(ch for ch in str(signal.get("pair", "")).upper() if ch.isalpha())
    variant = str(signal.get("variant", "config_default"))
    timestamp = _utc_stamp(signal.get("signal_close_utc") or signal.get("timestamp"))
    return f"{pair}:{timestamp}:{variant}"


def _finite_number(*values: Any, default: float = 0.0) -> float:
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            return number
    return default


def _structure_rank(signal: Mapping[str, Any]) -> int:
    evidence = signal.get("evidence") or {}
    structure = evidence.get("h1_structure") or {}
    state = str(structure.get("state", "")).upper()
    if state.endswith("_WEAK"):
        return 1
    if state in {"BULLISH", "BEARISH"}:
        return 2
    if state == "TRANSITION":
        return 0
    return -1


def _priority(signal: Mapping[str, Any]) -> int:
    variant = str(signal.get("variant", "config_default"))
    return int(VARIANTS.get(variant, {}).get("priority", 1000))


def _direction(signal: Mapping[str, Any]) -> str:
    side = str(signal.get("side", "")).upper()
    return {"BUY": "LONG", "SELL": "SHORT"}.get(side, side)


def _rank(signal: Mapping[str, Any]) -> tuple[Any, ...]:
    evidence = signal.get("evidence") or {}
    # The current canonical engine does not emit a separate quality score or a
    # statistically reliable validation-confidence field. They are optional,
    # and are ignored unless a future upstream contract supplies numeric values.
    quality = _finite_number(signal.get("quality_score"), evidence.get("quality_score"))
    rr = _finite_number(signal.get("rr"), signal.get("risk_reward"),
                        signal.get("planned_rr"))
    variant = str(signal.get("variant", "config_default"))
    identity = str(signal.get("signal_id") or signal_identity(signal))
    return (_priority(signal), -quality, -rr, -_structure_rank(signal), variant, identity)


def select_signals(
    scan_results: Iterable[Mapping[str, Any]],
    *,
    expected_variants: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Select one same-direction candidate, or explicitly reject an incomplete/conflicting set.

    All requested variants must have completed successfully before selection.
    Opposite-direction candidates always produce a conflict; no priority or
    iteration order is allowed to silently choose a direction.
    """
    results = list(scan_results)
    expected = tuple(expected_variants or ())
    observed = {str(result.get("variant", "config_default")) for result in results}
    missing = sorted(set(expected) - observed)
    unexpected = sorted(observed - set(expected)) if expected else []
    counts: dict[str, int] = {}
    for result in results:
        name = str(result.get("variant", "config_default"))
        counts[name] = counts.get(name, 0) + 1
    duplicates = sorted(name for name, count in counts.items() if count > 1)
    invalid_statuses = [
        {"variant": str(result.get("variant", "config_default")),
         "status": result.get("status")}
        for result in results
        if result.get("status") not in {"SIGNAL_ONLY", "NO_TRADE", "ERROR"}
    ]
    errors = [
        {"variant": str(result.get("variant", "config_default")),
         "error": result.get("error") or result.get("reason_codes") or "scan failed"}
        for result in results if result.get("status") == "ERROR"
    ]
    invalid_candidates = [
        str(result.get("variant", "config_default")) for result in results
        if result.get("status") == "SIGNAL_ONLY"
        and _direction(result) not in {"LONG", "SHORT"}
    ]
    if missing or unexpected or duplicates or invalid_statuses or errors or invalid_candidates:
        return {
            "status": "INCOMPLETE",
            "selected_signal": None,
            "candidate_signal_ids": [],
            "conflict": None,
            "missing_variants": missing,
            "unexpected_variants": unexpected,
            "duplicate_variants": duplicates,
            "invalid_statuses": invalid_statuses,
            "invalid_signal_variants": sorted(invalid_candidates),
            "scan_errors": errors,
            "reason": "All expected variants must finish before selecting a signal.",
        }

    candidates = [dict(result) for result in results if result.get("status") == "SIGNAL_ONLY"]
    for candidate in candidates:
        candidate["signal_id"] = str(candidate.get("signal_id") or signal_identity(candidate))
    candidate_ids = sorted(candidate["signal_id"] for candidate in candidates)
    if not candidates:
        return {
            "status": "NO_SIGNAL", "selected_signal": None,
            "candidate_signal_ids": [], "conflict": None,
            "missing_variants": [], "unexpected_variants": [],
            "duplicate_variants": [], "invalid_statuses": [],
            "invalid_signal_variants": [], "scan_errors": [],
        }

    directions = {_direction(candidate) for candidate in candidates}
    if len(directions) != 1:
        by_direction = {
            side: sorted(candidate["signal_id"] for candidate in candidates
                         if _direction(candidate) == side)
            for side in sorted(directions)
        }
        return {
            "status": "CONFLICT", "selected_signal": None,
            "candidate_signal_ids": candidate_ids,
            "conflict": {"type": "OPPOSING_VARIANT_DIRECTIONS", "signals_by_direction": by_direction},
            "missing_variants": [], "unexpected_variants": [],
            "duplicate_variants": [], "invalid_statuses": [],
            "invalid_signal_variants": [], "scan_errors": [],
        }

    selected = min(candidates, key=_rank)
    return {
        "status": "SELECTED", "selected_signal": selected,
        "selected_signal_id": selected["signal_id"],
        "candidate_signal_ids": candidate_ids,
        "selection_rule": [
            "explicit variant priority (lower value wins; current presets are intentionally tied)",
            "existing numeric signal quality score when supplied by the strategy",
            "risk/reward descending",
            "existing H1 structure strength",
            "stable variant name and signal identity",
        ],
        "historical_validation_confidence_used": False,
        "conflict": None, "missing_variants": [], "unexpected_variants": [],
        "duplicate_variants": [], "invalid_statuses": [],
        "invalid_signal_variants": [], "scan_errors": [],
    }
