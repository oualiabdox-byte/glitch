"""Volume-cycle based portfolio allocation with explicit look-ahead controls.

The component treats cTrader's native trendbar volume as tick volume. A cycle
closes only after its cumulative volume reaches a target derived from the
median volume of prior bars. Allocation for the next bar uses only cycles that
were completed before that bar; no future prices or volumes are used.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import exp, isfinite
from statistics import median
from typing import Any


def _utc(value: Any) -> datetime:
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


@dataclass(frozen=True)
class VolumeCycle:
    pair: str
    cycle_id: int
    start_time: str
    end_time: str
    start_index: int
    end_index: int
    bars: int
    volume: float
    target_volume: float
    return_pct: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "pair": self.pair,
            "cycle_id": self.cycle_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "start_index": self.start_index,
            "end_index": self.end_index,
            "bars": self.bars,
            "volume": self.volume,
            "target_volume": self.target_volume,
            "return_pct": self.return_pct,
        }


@dataclass(frozen=True)
class AllocatorConfig:
    target_cycle_bars: int = 96
    volume_lookback_bars: int = 96
    warmup_bars: int = 96
    history_cycles: int = 6
    ewma_alpha: float = 0.35
    vol_floor: float = 0.0005
    max_weight: float = 0.40
    temperature: float = 0.50
    min_weight: float = 0.0

    def __post_init__(self) -> None:
        if self.target_cycle_bars <= 0 or self.volume_lookback_bars <= 0 or self.warmup_bars <= 0:
            raise ValueError("cycle, lookback, and warmup bars must be positive")
        if not 0 < self.ewma_alpha <= 1 or self.history_cycles <= 0:
            raise ValueError("invalid history/ewma configuration")
        if self.vol_floor <= 0 or self.temperature <= 0:
            raise ValueError("vol_floor and temperature must be positive")
        if not 0 < self.max_weight <= 1:
            raise ValueError("max_weight must be in (0, 1]")
        if not 0 <= self.min_weight < 1:
            raise ValueError("min_weight must be in [0, 1)")


def validate_volume_bars(bars: list[dict[str, Any]], pair: str = "pair") -> dict[str, Any]:
    errors: list[str] = []
    previous: datetime | None = None
    positive = 0
    for index, row in enumerate(bars):
        try:
            timestamp = _utc(row["time"])
            values = [float(row[key]) for key in ("open", "high", "low", "close", "volume")]
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"{pair}:ROW_{index}_INVALID:{exc}")
            continue
        if previous is not None and timestamp <= previous:
            errors.append(f"{pair}:NON_MONOTONIC:{timestamp.isoformat()}")
        previous = timestamp
        if not all(isfinite(value) for value in values):
            errors.append(f"{pair}:NON_FINITE:{timestamp.isoformat()}")
        if values[2] > min(values[1], values[0], values[3]) or values[1] < max(values[0], values[3]) or values[1] < values[2]:
            errors.append(f"{pair}:OHLC_INVALID:{timestamp.isoformat()}")
        if values[4] <= 0:
            errors.append(f"{pair}:NON_POSITIVE_VOLUME:{timestamp.isoformat()}")
        else:
            positive += 1
    return {"pair": pair, "valid": not errors, "bars": len(bars), "positive_volume": positive, "errors": errors}


def build_volume_cycles(
    pair: str,
    bars: list[dict[str, Any]],
    config: AllocatorConfig = AllocatorConfig(),
) -> list[VolumeCycle]:
    """Build completed volume cycles using only prior-volume calibration.

    Bars before ``warmup_bars`` are calibration-only. At each cycle start the
    target is prior median volume multiplied by the desired cycle length.
    Incomplete final cycles are intentionally excluded.
    """
    report = validate_volume_bars(bars, pair)
    if not report["valid"]:
        raise ValueError("invalid volume bars: " + "; ".join(report["errors"][:5]))
    if len(bars) <= config.warmup_bars:
        return []

    cycles: list[VolumeCycle] = []
    start = config.warmup_bars
    cycle_id = 0
    while start < len(bars):
        prior = [float(row["volume"]) for row in bars[max(0, start - config.volume_lookback_bars):start]]
        if not prior or any(value <= 0 for value in prior):
            raise ValueError(f"{pair}: insufficient positive prior volume at index {start}")
        target = median(prior) * config.target_cycle_bars
        cumulative = 0.0
        end = start
        while end < len(bars) and cumulative < target:
            cumulative += float(bars[end]["volume"])
            end += 1
        if cumulative < target or end <= start:
            break
        end_index = end - 1
        start_close = float(bars[start]["close"])
        end_close = float(bars[end_index]["close"])
        if start_close <= 0:
            raise ValueError(f"{pair}: non-positive start close at index {start}")
        cycles.append(VolumeCycle(
            pair=pair,
            cycle_id=cycle_id,
            start_time=str(bars[start]["time"]),
            end_time=str(bars[end_index]["time"]),
            start_index=start,
            end_index=end_index,
            bars=end - start,
            volume=cumulative,
            target_volume=target,
            return_pct=end_close / start_close - 1.0,
        ))
        cycle_id += 1
        start = end
    return cycles


def _capped_normalize(raw: dict[str, float], max_weight: float) -> dict[str, float]:
    if not raw:
        return {}
    weights = {pair: 0.0 for pair in raw}
    remaining = set(raw)
    budget = 1.0
    while remaining:
        total = sum(max(0.0, raw[pair]) for pair in remaining)
        if total <= 0:
            share = budget / len(remaining)
            for pair in remaining:
                weights[pair] = share
            break
        capped = {pair for pair in remaining if budget * raw[pair] / total >= max_weight}
        if not capped:
            for pair in remaining:
                weights[pair] = budget * max(0.0, raw[pair]) / total
            break
        for pair in capped:
            weights[pair] = max_weight
            budget -= max_weight
            remaining.remove(pair)
        if budget <= 1e-12:
            break
    total = sum(weights.values())
    return {pair: value / total for pair, value in weights.items()} if total > 0 else {pair: 1 / len(weights) for pair in weights}


@dataclass
class AdaptiveAllocator:
    pairs: list[str]
    config: AllocatorConfig = field(default_factory=AllocatorConfig)
    histories: dict[str, list[float]] = field(init=False)

    def __post_init__(self) -> None:
        self.pairs = [str(pair).upper() for pair in self.pairs]
        if not self.pairs or len(set(self.pairs)) != len(self.pairs):
            raise ValueError("pairs must be non-empty and unique")
        self.histories = {pair: [] for pair in self.pairs}

    def weights(self) -> dict[str, float]:
        raw: dict[str, float] = {}
        for pair in self.pairs:
            history = self.histories[pair][-self.config.history_cycles:]
            if not history:
                raw[pair] = 1.0
                continue
            ewma = history[0]
            for value in history[1:]:
                ewma = self.config.ewma_alpha * value + (1 - self.config.ewma_alpha) * ewma
            mean_abs = sum(abs(value) for value in history) / len(history)
            momentum = max(0.0, ewma) / max(self.config.vol_floor, mean_abs)
            score = exp(min(20.0, momentum / self.config.temperature)) if momentum > 0 else 0.0
            raw[pair] = max(self.config.min_weight, score)
        # A cap below 1/N is mathematically infeasible when all capital must
        # remain allocated. Use the smallest feasible cap for small universes.
        feasible_cap = max(self.config.max_weight, 1.0 / len(self.pairs))
        return _capped_normalize(raw, feasible_cap)

    def record_completed_cycle(self, cycle: VolumeCycle) -> None:
        if cycle.pair not in self.histories:
            raise KeyError(cycle.pair)
        self.histories[cycle.pair].append(float(cycle.return_pct))


def simple_returns(bars: list[dict[str, Any]], timestamps: list[str]) -> dict[str, float]:
    by_time = {str(row["time"]): float(row["close"]) for row in bars}
    result: dict[str, float] = {}
    previous: float | None = None
    for timestamp in timestamps:
        current = by_time.get(timestamp)
        if current is None:
            continue
        if previous is not None and previous > 0:
            result[timestamp] = current / previous - 1.0
        previous = current
    return result


def max_drawdown(equity: list[float]) -> float:
    peak = 0.0
    worst = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1.0)
    return worst
