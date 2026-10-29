"""Explicit historical trading windows, with earlier observations retained for warmup."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime, timedelta

from .data import Bar, timestamp


def _boundary(value: str, *, end: bool) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Period dates must be ISO dates or timezone-aware timestamps")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        result = datetime.fromisoformat(value).replace(tzinfo=UTC)
        return result + timedelta(days=1) if end else result
    return timestamp(value)


def select_period(
    bars: list[Bar], period: dict | None, bar_seconds: float
) -> tuple[list[Bar], int, dict]:
    if period is None:
        period = {}
    if not isinstance(period, dict) or set(period) - {"start", "end", "last_bars"}:
        raise ValueError("Period supports start, end and last_bars only")
    if not math.isfinite(bar_seconds) or bar_seconds <= 0:
        raise ValueError("Set the true positive market bar duration")
    start = _boundary(period["start"], end=False) if period.get("start") else None
    end = _boundary(period["end"], end=True) if period.get("end") else None
    if start and end and start >= end:
        raise ValueError("The historical start must precede the end")
    duration = timedelta(seconds=bar_seconds)
    indices = [
        i
        for i, bar in enumerate(bars)
        if (start is None or bar.timestamp >= start)
        and (end is None or bar.timestamp + duration <= end)
    ]
    last = period.get("last_bars")
    if last is not None and last != "":
        if type(last) is not int or not 2 <= last <= 5000:
            raise ValueError("Choose 2..5,000 most recent bars, using an integer")
        indices = indices[-last:]
    if not 2 <= len(indices) <= 5000:
        raise ValueError("Choose a historical period containing 2..5,000 completed market bars")
    first, stop = indices[0], indices[-1] + 1
    # One thousand preceding bars cover the standard windows. Longer chained
    # expressions expose missing warmup instead of inventing prehistory.
    context = max(0, first - 1000)
    selected = bars[context:stop]
    active_start = first - context
    return (
        selected,
        active_start,
        {
            "requested": dict(period),
            "start": bars[first].timestamp.isoformat(),
            "end": (bars[stop - 1].timestamp + duration).isoformat(),
            "bars": len(indices),
            "warmup_bars": active_start,
            "excluded_before": context,
            "excluded_after": len(bars) - stop,
            "note": "Dates use UTC; an end date includes that complete day. Only completed bars ending by the chosen end are eligible. Up to 1,000 preceding bars are retained for trailing warmup; missing warmup stays missing.",
        },
    )
