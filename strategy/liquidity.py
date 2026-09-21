"""Price-structure liquidity detection for FX ICT/SMC research."""
from __future__ import annotations

from datetime import datetime, timezone

from . import market_structure


def _dt(value):
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _atr(candles, period=14):
    if len(candles) < 2:
        return 0.0
    start = max(1, len(candles) - period)
    trs = []
    for i in range(start, len(candles)):
        h, l = candles[i]["high"], candles[i]["low"]
        pc = candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else 0.0


def _previous_period_range(candles_4h, kind):
    if not candles_4h:
        return None, None
    current = _dt(candles_4h[-1]["time"])
    groups = {}
    for c in candles_4h:
        dt = _dt(c["time"])
        if kind == "day":
            key = dt.date()
        else:
            iso = dt.isocalendar()
            key = (iso.year, iso.week)
        groups.setdefault(key, []).append(c)

    if kind == "day":
        candidates = sorted(k for k in groups if k < current.date())
    else:
        current_key = (current.isocalendar().year, current.isocalendar().week)
        candidates = sorted(k for k in groups if k < current_key)
    if not candidates:
        return None, None
    bars = groups[candidates[-1]]
    return max(c["high"] for c in bars), min(c["low"] for c in bars)


def previous_day_high_low(candles_4h):
    return _previous_period_range(candles_4h, "day")


def previous_week_high_low(candles_4h):
    return _previous_period_range(candles_4h, "week")


def _cluster(points, tolerance_abs):
    points = sorted(points, key=lambda x: x["price"])
    clusters = []
    for point in points:
        if not clusters or point["price"] - clusters[-1][-1]["price"] > tolerance_abs:
            clusters.append([point])
        else:
            clusters[-1].append(point)
    return [
        {
            "price": sum(p["price"] for p in cluster) / len(cluster),
            "count": len(cluster),
            "first_time": cluster[0]["time"],
            "last_time": cluster[-1]["time"],
        }
        for cluster in clusters
        if len(cluster) >= 2
    ]


def equal_highs_lows(
    candles_1h,
    tolerance_pct=0.0005,
    swing_length=3,
    tolerance_atr=0.15,
):
    """Cluster confirmed swing highs/lows into EQH/EQL pools."""
    if len(candles_1h) < swing_length * 2 + 1:
        return [], []

    highs = market_structure.find_swing_highs(candles_1h, length=swing_length)
    lows = market_structure.find_swing_lows(candles_1h, length=swing_length)
    atr = _atr(candles_1h)
    avg_price = sum(c["close"] for c in candles_1h) / max(1, len(candles_1h))
    tolerance = max(avg_price * tolerance_pct, atr * tolerance_atr)

    eqh = _cluster(
        [{"price": x["high"], "time": x["time"]} for x in highs],
        tolerance,
    )
    eql = _cluster(
        [{"price": x["low"], "time": x["time"]} for x in lows],
        tolerance,
    )
    return eqh, eql


def liquidity_pools(candles_4h, swing_length=2, eq_tolerance_atr=0.15):
    pools = []
    pdh, pdl = previous_day_high_low(candles_4h)
    pwh, pwl = previous_week_high_low(candles_4h)

    if pdh is not None:
        pools.append({"type": "resistance", "price": pdh, "source": "PDH", "strength": "medium"})
    if pdl is not None:
        pools.append({"type": "support", "price": pdl, "source": "PDL", "strength": "medium"})
    if pwh is not None:
        pools.append({"type": "resistance", "price": pwh, "source": "PWH", "strength": "high"})
    if pwl is not None:
        pools.append({"type": "support", "price": pwl, "source": "PWL", "strength": "high"})

    eqh, eql = equal_highs_lows(
        candles_4h[-30:],
        swing_length=swing_length,
        tolerance_atr=eq_tolerance_atr,
    )
    for e in eqh:
        pools.append({
            "type": "resistance",
            "price": e["price"],
            "source": "EQH",
            "strength": "high" if e["count"] >= 3 else "medium",
            "count": e["count"],
        })
    for e in eql:
        pools.append({
            "type": "support",
            "price": e["price"],
            "source": "EQL",
            "strength": "high" if e["count"] >= 3 else "medium",
            "count": e["count"],
        })
    return pools
