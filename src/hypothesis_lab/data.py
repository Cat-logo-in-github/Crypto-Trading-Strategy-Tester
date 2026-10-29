"""Validated market bars and point-in-time external observations."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


def timestamp(value: str | datetime) -> datetime:
    result = (
        datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    )
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Timestamps must include a timezone, for example 2024-01-01T00:00:00Z")
    return result.astimezone(UTC)


@dataclass(frozen=True)
class Bar:
    """One completed interval. timestamp is its OPEN time; close is available at interval end."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", timestamp(self.timestamp))
        values = (self.open, self.high, self.low, self.close, self.volume)
        if not all(math.isfinite(x) for x in values):
            raise ValueError("Bar values must be finite")
        if min(values[:4]) <= 0 or self.volume < 0:
            raise ValueError("OHLC must be positive and volume nonnegative")
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("Low/high must contain open and close")
        if self.low > self.high:
            raise ValueError("Low must not exceed high")


@dataclass(frozen=True)
class Event:
    observed_at: datetime
    available_at: datetime
    value: float
    field: str = "temperature"
    location: str = "Synthetic town"

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", timestamp(self.observed_at))
        object.__setattr__(self, "available_at", timestamp(self.available_at))
        if self.available_at < self.observed_at or not math.isfinite(self.value):
            raise ValueError("Events require finite values and availability at/after observation")


def validate_bars(bars: list[Bar]) -> list[Bar]:
    if len(bars) < 2:
        raise ValueError("At least two completed market bars are required")
    if any(b.timestamp <= a.timestamp for a, b in zip(bars, bars[1:])):
        raise ValueError("Market bars must be strictly chronological; duplicates are rejected")
    return bars


def load_bars(source: str | Path, *, content: bool = False) -> list[Bar]:
    text = str(source) if content else Path(source).read_text(encoding="utf-8-sig")
    rows = csv.DictReader(io.StringIO(text))
    required = {"timestamp", "open", "high", "low", "close"}
    if not required.issubset(rows.fieldnames or []):
        raise ValueError("Market CSV requires timestamp,open,high,low,close; volume is optional")
    bars = []
    for row in rows:
        bars.append(
            Bar(
                timestamp(row["timestamp"]),
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
                float(row.get("volume") or 0),
            )
        )
        if len(bars) > 100_000:
            raise ValueError("CSV exceeds the 100,000-bar interactive limit")
    return validate_bars(bars)


def load_events(source: str | Path, *, content: bool = False) -> list[Event]:
    text = str(source) if content else Path(source).read_text(encoding="utf-8-sig")
    rows = csv.DictReader(io.StringIO(text))
    if not {"observed_at", "available_at", "value"}.issubset(rows.fieldnames or []):
        raise ValueError(
            "Event CSV requires observed_at,available_at,value; field,location optional"
        )
    events = [
        Event(
            timestamp(r["observed_at"]),
            timestamp(r["available_at"]),
            float(r["value"]),
            r.get("field") or "temperature",
            r.get("location") or "User location",
        )
        for r in rows
    ]
    keys = [(e.observed_at, e.available_at, e.field, e.location) for e in events]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate event revisions are ambiguous")
    if len(events) > 100_000:
        raise ValueError("Too many external observations")
    return sorted(events, key=lambda e: e.available_at)


def available_value(
    events: list[Event],
    when: datetime,
    *,
    field: str = "temperature",
    location: str | None = None,
    max_age_hours: float = 48,
) -> float | None:
    """Latest observed value among revisions published by `when`, with explicit expiry."""
    if not math.isfinite(max_age_hours) or max_age_hours <= 0:
        raise ValueError("Event maximum age must be positive and finite")
    eligible = [
        e
        for e in events
        if e.available_at <= when
        and e.observed_at <= when
        and e.field == field
        and (location is None or e.location == location)
    ]
    if not eligible:
        return None
    event = max(eligible, key=lambda e: (e.observed_at, e.available_at))
    if (when - event.observed_at).total_seconds() > max_age_hours * 3600:
        return None
    return event.value


def fingerprint(bars: list[Bar], events: list[Event] | None = None) -> str:
    raw = json.dumps(
        {"bars": [asdict(b) for b in bars], "events": [asdict(e) for e in events or []]},
        default=str,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def fixtures() -> tuple[list[Bar], list[Event]]:
    base = Path(__file__).with_name("fixtures")
    return load_bars(base / "market.csv"), load_events(base / "weather.csv")
