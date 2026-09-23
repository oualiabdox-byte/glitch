"""Causal 1D/1H/5M SMC research engine.

This module is intentionally separate from the legacy H1/H4 evaluator. It is a
closed-bar research engine: daily bias is available only after a D1 close,
H1 pivots only after their right-side confirmation bars, and M5 orders only on
the bar after a closed rejection trigger. Community labels (IRL/ERL, breaker,
mitigation and Unicorn) are represented as explicit OHLC rules, not claims
about observable institutional order flow.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Iterable


@dataclass(frozen=True)
class Pivot:
    side: str
    price: float
    pivot_idx: int
    confirmed_idx: int


@dataclass(frozen=True)
class FVG:
    side: str
    bottom: float
    top: float
    created_idx: int
    status: str = "UNTOUCHED"


@dataclass(frozen=True)
class DailyBias:
    state: str
    strength: str
    reason: str
    availability_idx: int
    effective_idx: int
    pdh: float | None
    pdl: float | None
    equilibrium: float | None
    premium_discount: str | None


def _atr(candles: list[dict], end_idx: int, period: int = 14) -> float:
    if end_idx < 1:
        return 0.0
    start = max(1, end_idx - period + 1)
    trs = []
    for i in range(start, end_idx + 1):
        h, low = candles[i]["high"], candles[i]["low"]
        pc = candles[i - 1]["close"]
        trs.append(max(h - low, abs(h - pc), abs(low - pc)))
    return sum(trs) / len(trs) if trs else 0.0


def _validate_bar(c: dict) -> None:
    if c["high"] < c["low"]:
        raise ValueError("high must be >= low")
    if not c["low"] <= c["open"] <= c["high"]:
        raise ValueError("open must be inside candle range")
    if not c["low"] <= c["close"] <= c["high"]:
        raise ValueError("close must be inside candle range")


def daily_bias(candles: list[dict], end_idx: int | None = None, tick_size: float = 1e-5) -> DailyBias:
    """Classify the next session from the last two completed daily candles."""
    last = len(candles) - 1 if end_idx is None else int(end_idx)
    if last < 1:
        return DailyBias("NEUTRAL", "NONE", "INSUFFICIENT_DAILY_HISTORY", last, last + 1, None, None, None, None)
    for c in candles[: last + 1]:
        _validate_bar(c)
    prev, cur = candles[last - 1], candles[last]
    eps = max(tick_size, 0.0)
    pdh, pdl = prev["high"], prev["low"]
    eq = (pdh + pdl) / 2.0
    if pdh - pdl <= eps:
        return DailyBias("NEUTRAL", "NONE", "INVALID_OR_DEGENERATE_RANGE", last, last + 1, pdh, pdl, eq, "EQUILIBRIUM")
    bull_break = cur["close"] > pdh + eps
    bear_break = cur["close"] < pdl - eps
    low_sweep = cur["low"] < pdl - eps
    high_sweep = cur["high"] > pdh + eps
    bull_reclaim = low_sweep and cur["close"] > pdl + eps and cur["close"] >= eq - eps
    bear_reclaim = high_sweep and cur["close"] < pdh - eps and cur["close"] <= eq + eps
    if bull_break and not bear_break:
        state, strength, reason = "BULLISH", "CONFIRMED", "CLOSE_ABOVE_PDH"
    elif bear_break and not bull_break:
        state, strength, reason = "BEARISH", "CONFIRMED", "CLOSE_BELOW_PDL"
    elif bull_reclaim and not bear_reclaim:
        state, strength, reason = "BULLISH", "CONFIRMED_RECLAIM", "SWEEP_PDL_RECLAIM_ABOVE_EQ"
    elif bear_reclaim and not bull_reclaim:
        state, strength, reason = "BEARISH", "CONFIRMED_RECLAIM", "SWEEP_PDH_REJECT_BELOW_EQ"
    else:
        state, strength, reason = "NEUTRAL", "NONE", "NO_CLOSED_DIRECTIONAL_CONFIRMATION"
    location = "PREMIUM" if cur["close"] > eq + eps else "DISCOUNT" if cur["close"] < eq - eps else "EQUILIBRIUM"
    return DailyBias(state, strength, reason, last, last + 1, pdh, pdl, eq, location)


def confirmed_pivots(candles: list[dict], end_idx: int | None = None, radius: int = 3) -> list[Pivot]:
    """Return only pivots whose right-side confirmation bars are available."""
    if radius < 1:
        raise ValueError("radius must be >= 1")
    last = len(candles) - 1 if end_idx is None else int(end_idx)
    out: list[Pivot] = []
    for i in range(radius, min(last - radius, len(candles) - radius - 1) + 1):
        left = candles[i - radius:i]
        right = candles[i + 1:i + radius + 1]
        high = candles[i]["high"]
        low = candles[i]["low"]
        if high > max(x["high"] for x in left) and high > max(x["high"] for x in right):
            out.append(Pivot("HIGH", high, i, i + radius))
        if low < min(x["low"] for x in left) and low < min(x["low"] for x in right):
            out.append(Pivot("LOW", low, i, i + radius))
    return out


def _alternating(pivots: list[Pivot]) -> list[Pivot]:
    result: list[Pivot] = []
    for p in sorted(pivots, key=lambda x: (x.confirmed_idx, x.pivot_idx)):
        if result and result[-1].side == p.side:
            replace = p.price > result[-1].price if p.side == "HIGH" else p.price < result[-1].price
            if replace:
                result[-1] = p
        else:
            result.append(p)
    return result


def _body_metrics(candle: dict, atr: float) -> dict[str, float | bool]:
    rng = max(candle["high"] - candle["low"], 0.0)
    body = abs(candle["close"] - candle["open"])
    return {
        "body_atr": body / atr if atr > 0 else 0.0,
        "body_range": body / rng if rng > 0 else 0.0,
        "directional": candle["close"] > candle["open"] if body > 0 else False,
    }


def h1_structure(candles: list[dict], end_idx: int | None = None, radius: int = 3,
                  break_buffer_atr: float = 0.10, displacement_body_atr: float = 1.0,
                  displacement_body_range: float = 0.60) -> dict[str, Any]:
    """Return current causal H1 structure and one event at the last close."""
    last = len(candles) - 1 if end_idx is None else int(end_idx)
    pivots = _alternating(confirmed_pivots(candles, last, radius))
    highs = [p for p in pivots if p.side == "HIGH"]
    lows = [p for p in pivots if p.side == "LOW"]
    state = "RANGE"
    if len(highs) >= 2 and len(lows) >= 2:
        bullish = highs[-1].price > highs[-2].price and lows[-1].price > lows[-2].price
        bearish = highs[-1].price < highs[-2].price and lows[-1].price < lows[-2].price
        state = "BULL" if bullish else "BEAR" if bearish else "RANGE"
    if last < 1 or not pivots:
        return {"state": state, "event": None, "pivots": pivots, "external_high": highs[-1].price if highs else None, "external_low": lows[-1].price if lows else None}
    atr = _atr(candles, last)
    buffer = max(break_buffer_atr * atr, 0.0)
    close = candles[last]["close"]
    event = None
    if state == "BULL" and highs and close > highs[-1].price + buffer:
        event = {"type": "BOS", "side": "BULLISH", "level": highs[-1].price, "idx": last, "displacement": _body_metrics(candles[last], atr)}
    elif state == "BULL" and lows and close < lows[-1].price - buffer:
        metrics = _body_metrics(candles[last], atr)
        event = {"type": "MSS" if metrics["body_atr"] >= displacement_body_atr and metrics["body_range"] >= displacement_body_range else "CHOCH", "side": "BEARISH", "level": lows[-1].price, "idx": last, "displacement": metrics}
    elif state == "BEAR" and lows and close < lows[-1].price - buffer:
        event = {"type": "BOS", "side": "BEARISH", "level": lows[-1].price, "idx": last, "displacement": _body_metrics(candles[last], atr)}
    elif state == "BEAR" and highs and close > highs[-1].price + buffer:
        metrics = _body_metrics(candles[last], atr)
        event = {"type": "MSS" if metrics["body_atr"] >= displacement_body_atr and metrics["body_range"] >= displacement_body_range else "CHOCH", "side": "BULLISH", "level": highs[-1].price, "idx": last, "displacement": metrics}
    return {"state": state, "event": event, "pivots": pivots, "external_high": highs[-1].price if highs else None, "external_low": lows[-1].price if lows else None}


def detect_fvg(candles: list[dict], end_idx: int | None = None, side: str | None = None,
               min_width_atr: float = 0.10, tick_size: float = 1e-5) -> FVG | None:
    last = len(candles) - 1 if end_idx is None else int(end_idx)
    if last < 2:
        return None
    atr = _atr(candles, last - 1)
    a, mid, c = candles[last - 2], candles[last - 1], candles[last]
    if c["low"] > a["high"]:
        found = FVG("BULLISH", a["high"], c["low"], last)
    elif c["high"] < a["low"]:
        found = FVG("BEARISH", c["high"], a["low"], last)
    else:
        return None
    if side and found.side != side:
        return None
    metrics = _body_metrics(mid, atr)
    if found.top - found.bottom < max(2 * tick_size, min_width_atr * atr):
        return None
    if not metrics["directional"] or metrics["body_atr"] < 0.50 or metrics["body_range"] < 0.50:
        return None
    return found


def liquidity_pools(candles: list[dict], end_idx: int | None = None, radius: int = 3,
                    pool_tolerance_atr: float = 0.10) -> list[dict[str, Any]]:
    last = len(candles) - 1 if end_idx is None else int(end_idx)
    atr = _atr(candles, last)
    eps = max(atr * pool_tolerance_atr, 1e-9)
    pools = []
    for p in _alternating(confirmed_pivots(candles, last, radius)):
        if not any(x["side"] == p.side and abs(x["price"] - p.price) <= eps for x in pools):
            pools.append({"side": "BUY_SIDE" if p.side == "HIGH" else "SELL_SIDE", "price": p.price, "confirmed_idx": p.confirmed_idx, "swept": False})
    return pools


def transition_state(m5: list[dict], parent_low: float | None, parent_high: float | None,
                     side: str, end_idx: int | None = None, radius: int = 3,
                     sweep_buffer_atr: float = 0.10, break_buffer_atr: float = 0.10) -> dict[str, Any]:
    """Find the latest internal sweep -> reclaim -> displacement transition."""
    last = len(m5) - 1 if end_idx is None else int(end_idx)
    if parent_low is None or parent_high is None or parent_low >= parent_high:
        return {"state": "NO_RANGE", "signal": None}
    pools = liquidity_pools(m5, last, radius)
    internal = [p for p in pools if parent_low < p["price"] < parent_high]
    wanted_pool_side = "SELL_SIDE" if side == "LONG" else "BUY_SIDE"
    candidates = [p for p in internal if p["side"] == wanted_pool_side and p["confirmed_idx"] < last]
    if not candidates:
        return {"state": "INTERNAL_ARMED", "signal": None, "pools": pools}
    pool = candidates[-1]
    atr = _atr(m5, last)
    for sweep_idx in range(max(pool["confirmed_idx"] + 1, last - 8), last + 1):
        sweep = m5[sweep_idx]
        swept = sweep["low"] < pool["price"] - sweep_buffer_atr * atr if side == "LONG" else sweep["high"] > pool["price"] + sweep_buffer_atr * atr
        reclaimed = sweep["close"] >= pool["price"] if side == "LONG" else sweep["close"] <= pool["price"]
        if not (swept and reclaimed):
            continue
        prior = _alternating(confirmed_pivots(m5, sweep_idx - 1, radius))
        opposite = [p for p in prior if p.side == "HIGH" if side == "LONG"] if side == "LONG" else [p for p in prior if p.side == "LOW"]
        if not opposite:
            continue
        level = opposite[-1].price
        for break_idx in range(sweep_idx + 1, last + 1):
            b = m5[break_idx]
            br_atr = _atr(m5, break_idx)
            metrics = _body_metrics(b, br_atr)
            broken = b["close"] > level + break_buffer_atr * br_atr if side == "LONG" else b["close"] < level - break_buffer_atr * br_atr
            if broken and metrics["body_atr"] >= 0.75 and metrics["body_range"] >= 0.50:
                return {"state": "DISPLACEMENT_CONFIRMED", "signal": {"side": side, "pool": pool, "sweep_idx": sweep_idx, "break_idx": break_idx, "break_level": level, "sweep_extreme": sweep["low"] if side == "LONG" else sweep["high"]}}
    return {"state": "INTERNAL_SWEPT", "signal": None, "pools": pools}


def evaluate_setup(d1: list[dict], h1: list[dict], m5: list[dict], end_idx: int | None = None,
                   tick_size: float = 1e-5, require_unicorn: bool = False) -> dict[str, Any] | None:
    """Evaluate one M5 close. Returns a setup only after a closed rejection bar."""
    if len(d1) < 2 or len(h1) < 20 or len(m5) < 30:
        return None
    d_bias = daily_bias(d1, tick_size=tick_size)
    if d_bias.state not in {"BULLISH", "BEARISH"}:
        return None
    h = h1[-1]
    structure = h1_structure(h1)
    if structure["state"] not in {"BULL", "BEAR"}:
        return None
    side = "LONG" if d_bias.state == "BULLISH" else "SHORT"
    if (side == "LONG" and structure["state"] != "BULL") or (side == "SHORT" and structure["state"] != "BEAR"):
        return None
    transition = transition_state(m5, structure["external_low"], structure["external_high"], side)
    if transition.get("state") != "DISPLACEMENT_CONFIRMED":
        return None
    sig = transition["signal"]
    fvg = detect_fvg(m5, sig["break_idx"], "BULLISH" if side == "LONG" else "BEARISH", tick_size=tick_size)
    if not fvg:
        return None
    from .unicorn import find_unicorn_zone
    unicorn = find_unicorn_zone(m5, side, sig["break_idx"], tick_size=tick_size)
    if require_unicorn and not unicorn:
        return None
    for i in range(sig["break_idx"] + 1, min(len(m5), sig["break_idx"] + 5)):
        bar = m5[i]
        touched = bar["low"] <= fvg.top and bar["high"] >= fvg.bottom
        rejected = bar["close"] > fvg.top if side == "LONG" else bar["close"] < fvg.bottom
        if touched and rejected:
            if i != len(m5) - 1:
                continue
            return {"side": side, "entry_idx": i + 1, "entry_price": None, "stop_extreme": sig["sweep_extreme"], "fvg": asdict(fvg), "unicorn": unicorn, "transition": sig, "daily_bias": asdict(d_bias), "h1_structure": {"state": structure["state"], "event": structure["event"]}, "unicorn_required": require_unicorn, "entry_model": "D1_H1_M5_SWEEP_FVG_REJECTION"}
    return None


def evaluate_stream(d1: list[dict], h1: list[dict], m5: list[dict], tick_size: float = 1e-5) -> list[dict[str, Any]]:
    """Deterministic smoke-test helper; each returned signal uses a closed M5 prefix."""
    signals = []
    for i in range(30, len(m5)):
        setup = evaluate_setup(d1, h1, m5[: i + 1], tick_size=tick_size)
        if setup:
            setup["signal_m5_idx"] = i
            signals.append(setup)
    return signals


__all__ = ["DailyBias", "FVG", "Pivot", "daily_bias", "confirmed_pivots", "h1_structure", "detect_fvg", "liquidity_pools", "transition_state", "evaluate_setup", "evaluate_stream"]


if __name__ == "__main__":
    raise SystemExit("Import this module from the strategy or backtest runner; it is not a CLI.")


# Keep Iterable referenced for type-checkers in older Python environments.
_ = Iterable
