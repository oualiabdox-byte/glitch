"""Chronological walk-forward splits for leakage-resistant evaluation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class WalkForwardWindow:
    index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    embargo_bars: int


def build_walk_forward_windows(timestamps: Sequence[T], train_bars: int, test_bars: int, step_bars: int | None = None, embargo_bars: int = 0) -> list[WalkForwardWindow]:
    """Build rolling train/test windows without shuffling or test reuse."""
    count = len(timestamps)
    if train_bars < 1 or test_bars < 1:
        raise ValueError("train_bars and test_bars must be >= 1")
    if embargo_bars < 0:
        raise ValueError("embargo_bars must be >= 0")
    step = test_bars if step_bars is None else step_bars
    if step < 1:
        raise ValueError("step_bars must be >= 1")
    windows = []
    start = 0
    index = 0
    while True:
        train_end = start + train_bars
        test_start = train_end + embargo_bars
        test_end = test_start + test_bars
        if test_end > count:
            break
        windows.append(WalkForwardWindow(index, start, train_end, test_start, test_end, embargo_bars))
        index += 1
        start += step
    return windows
