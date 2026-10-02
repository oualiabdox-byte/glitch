"""Adaptive portfolio allocation with explicit risk and correlation controls.

Research-only allocation layer. It does not create trading signals and it never
uses future returns to score a signal. Call ``allocate`` at one decision time
with already-valid candidates and point-in-time statistics for each candidate.

Default policy:
- base risk: 0.25% of current equity per accepted trade;
- portfolio open-risk cap: 1.00%;
- same-currency exposure cap: 0.50%;
- correlated-cluster cap: 0.50%;
- pair risk cap: 0.25% (the base risk);
- candidates are ranked by conservative quality score, then stable identity;
- a candidate is accepted only if its marginal correlation exposure fits the
  remaining cluster and portfolio budgets.

The correlation matrix is an input estimated from a prior rolling return
window. Missing correlations are treated as zero for pairwise exposure but the
currency-cluster rule remains active as a conservative backstop.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class AllocationConfig:
    risk_per_trade: float = 0.0025
    max_portfolio_risk: float = 0.0100
    max_currency_cluster_risk: float = 0.0050
    max_correlated_cluster_risk: float = 0.0050
    max_open_positions: int = 4
    correlation_threshold: float = 0.70
    score_floor: float = 0.45
    uncertainty_penalty: float = 0.20

    def __post_init__(self) -> None:
        for name in ("risk_per_trade", "max_portfolio_risk", "max_currency_cluster_risk", "max_correlated_cluster_risk"):
            value = float(getattr(self, name))
            if not 0 < value <= 1:
                raise ValueError(f"{name} must be in (0, 1]")
        if self.risk_per_trade > self.max_portfolio_risk:
            raise ValueError("risk_per_trade cannot exceed max_portfolio_risk")
        if self.max_open_positions <= 0:
            raise ValueError("max_open_positions must be positive")
        if not 0 < self.correlation_threshold <= 1:
            raise ValueError("correlation_threshold must be in (0, 1]")
        if not 0 <= self.score_floor <= 1 or not 0 <= self.uncertainty_penalty <= 1:
            raise ValueError("score_floor and uncertainty_penalty must be in [0, 1]")


@dataclass(frozen=True)
class Candidate:
    """A signal eligible for allocation at one point in time."""

    signal_id: str
    pair: str
    side: str
    quality_score: float
    historical_expectancy_r: float = 0.0
    sample_size: int = 0
    currency_cluster: str | None = None
    correlation_cluster: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.signal_id or not self.pair:
            raise ValueError("signal_id and pair are required")
        if self.side.upper() not in {"LONG", "SHORT", "BUY", "SELL"}:
            raise ValueError("side must be LONG/SHORT or BUY/SELL")
        if not isfinite(float(self.quality_score)) or not 0 <= self.quality_score <= 1:
            raise ValueError("quality_score must be finite and in [0, 1]")
        if not isfinite(float(self.historical_expectancy_r)):
            raise ValueError("historical_expectancy_r must be finite")
        if self.sample_size < 0:
            raise ValueError("sample_size cannot be negative")


@dataclass(frozen=True)
class AllocationDecision:
    signal_id: str
    pair: str
    accepted: bool
    allocated_risk: float
    score: float
    reason: str
    portfolio_risk_after: float
    currency_risk_after: float
    correlated_risk_after: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id, "pair": self.pair,
            "accepted": self.accepted, "allocated_risk": self.allocated_risk,
            "score": self.score, "reason": self.reason,
            "portfolio_risk_after": self.portfolio_risk_after,
            "currency_risk_after": self.currency_risk_after,
            "correlated_risk_after": self.correlated_risk_after,
        }


def _pair_key(pair: str) -> str:
    return str(pair).upper().replace("/", "")


def default_currency_cluster(pair: str) -> str:
    """Return a conservative currency-exposure cluster for major FX pairs."""
    key = _pair_key(pair)
    if key in {"EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"}:
        return "USD_QUOTED"
    if key in {"USDJPY", "USDCHF", "USDCAD"}:
        return "USD_BASE"
    if key in {"EURGBP", "EURAUD", "EURJPY", "EURCHF"}:
        return "EUR_CROSS"
    if key in {"XAUUSD", "GOLD", "GC=F"}:
        return "USD_GOLD"
    return key


def default_correlation_cluster(pair: str) -> str:
    key = _pair_key(pair)
    if key in {"EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY"}:
        return "USD_MAJOR"
    if key in {"XAUUSD", "GOLD", "GC=F"}:
        return "GOLD_USD"
    return key


def conservative_score(candidate: Candidate, config: AllocationConfig) -> float:
    """Score only prior-known quality, expectancy, and sample uncertainty."""
    sample_confidence = min(1.0, candidate.sample_size / 100.0)
    expectancy_component = min(1.0, max(0.0, 0.5 + candidate.historical_expectancy_r / 2.0))
    uncertainty_adjusted = (1.0 - config.uncertainty_penalty * (1.0 - sample_confidence))
    return max(0.0, min(1.0, candidate.quality_score * (0.65 + 0.35 * expectancy_component) * uncertainty_adjusted))


def _correlation(a: str, b: str, correlations: Mapping[tuple[str, str], float]) -> float:
    if a == b:
        return 1.0
    value = correlations.get((a, b), correlations.get((b, a), 0.0))
    return abs(float(value))


def allocate(
    candidates: Sequence[Candidate],
    *,
    config: AllocationConfig = AllocationConfig(),
    correlations: Mapping[tuple[str, str], float] | None = None,
    existing: Sequence[Candidate] = (),
    existing_allocations: Mapping[str, float] | None = None,
) -> list[AllocationDecision]:
    """Rank and allocate candidates at one timestamp without look-ahead.

    ``correlations`` must be calculated from data ending before the decision.
    Existing positions consume risk budgets before new candidates are evaluated.
    A signal is rejected rather than fractionally resized: this keeps the
    contract easy to audit and avoids silently changing per-trade risk.
    """
    correlations = correlations or {}
    existing_allocations = {str(k): float(v) for k, v in (existing_allocations or {}).items()}
    if any(value < 0 for value in existing_allocations.values()):
        raise ValueError("existing allocations cannot be negative")
    portfolio_risk = sum(existing_allocations.values())
    currency_risk: dict[str, float] = {}
    correlated_risk: dict[str, float] = {}
    pair_risk: dict[str, float] = {}
    allocated_positions: list[tuple[Candidate, float]] = []
    for position in existing:
        amount = existing_allocations.get(position.signal_id, 0.0)
        cluster = position.currency_cluster or default_currency_cluster(position.pair)
        corr_cluster = position.correlation_cluster or default_correlation_cluster(position.pair)
        currency_risk[cluster] = currency_risk.get(cluster, 0.0) + amount
        correlated_risk[corr_cluster] = correlated_risk.get(corr_cluster, 0.0) + amount
        pair_risk[_pair_key(position.pair)] = pair_risk.get(_pair_key(position.pair), 0.0) + amount
        allocated_positions.append((position, amount))
    if portfolio_risk > config.max_portfolio_risk + 1e-12:
        raise ValueError("existing allocations exceed max_portfolio_risk")

    ranked = sorted(candidates, key=lambda c: (-conservative_score(c, config), str(c.signal_id)))
    decisions: list[AllocationDecision] = []
    accepted_pairs = {_pair_key(p.pair) for p in existing}
    for candidate in ranked:
        score = conservative_score(candidate, config)
        pair = _pair_key(candidate.pair)
        currency = candidate.currency_cluster or default_currency_cluster(pair)
        corr_cluster = candidate.correlation_cluster or default_correlation_cluster(pair)
        corr_exposure = correlated_risk.get(corr_cluster, 0.0)
        for position, position_amount in allocated_positions:
            if _correlation(pair, _pair_key(position.pair), correlations) >= config.correlation_threshold:
                position_cluster = position.correlation_cluster or default_correlation_cluster(position.pair)
                if position_cluster != corr_cluster:
                    corr_exposure += position_amount
        reason = "accepted"
        accepted = True
        amount = config.risk_per_trade
        if score < config.score_floor:
            accepted, reason = False, "quality_below_floor"
        elif len(accepted_pairs) >= config.max_open_positions:
            accepted, reason = False, "max_open_positions"
        elif portfolio_risk + amount > config.max_portfolio_risk + 1e-12:
            accepted, reason = False, "portfolio_risk_cap"
        elif pair_risk.get(pair, 0.0) + amount > config.risk_per_trade + 1e-12:
            accepted, reason = False, "pair_risk_cap"
        elif currency_risk.get(currency, 0.0) + amount > config.max_currency_cluster_risk + 1e-12:
            accepted, reason = False, "currency_cluster_cap"
        elif corr_exposure + amount > config.max_correlated_cluster_risk + 1e-12:
            accepted, reason = False, "correlation_cluster_cap"
        if accepted:
            portfolio_risk += amount
            currency_risk[currency] = currency_risk.get(currency, 0.0) + amount
            correlated_risk[corr_cluster] = correlated_risk.get(corr_cluster, 0.0) + amount
            pair_risk[pair] = pair_risk.get(pair, 0.0) + amount
            accepted_pairs.add(pair)
            allocated_positions.append((candidate, amount))
        decisions.append(AllocationDecision(candidate.signal_id, candidate.pair, accepted, amount if accepted else 0.0,
                                            score, reason, portfolio_risk,
                                            currency_risk.get(currency, 0.0), corr_exposure + (amount if accepted else 0.0)))
    return decisions


def allocation_policy_summary(config: AllocationConfig = AllocationConfig()) -> dict[str, Any]:
    return {
        "risk_per_trade_pct": config.risk_per_trade * 100,
        "max_portfolio_risk_pct": config.max_portfolio_risk * 100,
        "max_currency_cluster_risk_pct": config.max_currency_cluster_risk * 100,
        "max_correlated_cluster_risk_pct": config.max_correlated_cluster_risk * 100,
        "max_open_positions": config.max_open_positions,
        "correlation_threshold": config.correlation_threshold,
        "score_floor": config.score_floor,
        "lookahead_rule": "quality, expectancy, and correlations must be estimated only from data available before decision time",
    }
