"""Structural Fibonacci cluster confluence.

This module never creates a trade by itself. It only measures whether a
retracement/extension cluster is near a structural price area.
"""

def fibonacci_levels(high, low):
    if high <= low:
        raise ValueError("high must be greater than low")
    span = high - low
    return {
        "0.500": low + span * 0.500,
        "0.618": low + span * 0.618,
        "0.705": low + span * 0.705,
        "0.786": low + span * 0.786,
    }


def cluster(levels, tolerance):
    if tolerance < 0:
        raise ValueError("tolerance must be >= 0")
    points = sorted(levels.items(), key=lambda x: x[1])
    groups = []
    for name, price in points:
        if not groups or price - groups[-1][-1][1] > tolerance:
            groups.append([(name, price)])
        else:
            groups[-1].append((name, price))
    return [
        {
            "price": sum(p for _, p in group) / len(group),
            "levels": [n for n, _ in group],
            "count": len(group),
        }
        for group in groups
        if len(group) >= 2
    ]


def find_cluster(high, low, tolerance):
    levels = fibonacci_levels(high, low)
    clusters = cluster(levels, tolerance)
    return {
        "levels": levels,
        "clusters": clusters,
        "best": max(clusters, key=lambda x: x["count"]) if clusters else None,
    }
