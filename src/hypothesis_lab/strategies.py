"""Deterministic supported patterns and composable, causal rule trees."""

from __future__ import annotations

import math
import re
from datetime import timedelta
from typing import Protocol

from .data import Bar, Event, available_value
from .engine import Decision


class Strategy(Protocol):
    def decide(self, history: tuple[Bar, ...]) -> Decision | None: ...


def sma(values: list[float], window: int) -> float | None:
    if isinstance(window, bool) or not isinstance(window, int) or not 1 <= window <= 1000:
        raise ValueError("Indicator window must be 1..1000")
    return (
        math.fsum(value / window for value in values[-window:]) if len(values) >= window else None
    )


def feature(name: str, bars: list[Bar], i: int, events: list[Event], spec: dict) -> float | None:
    aligned = spec.get("_aligned_features")
    external_name = name[6:] if name.startswith("event:") else name
    closes = [b.close for b in bars[: i + 1]]
    if name == "close":
        return closes[-1]
    if name.startswith("sma_"):
        return sma(closes, int(name[4:]))
    if name.startswith("momentum_"):
        window = int(name[9:])
        if not 1 <= window <= 1000:
            raise ValueError("Momentum window must be 1..1000")
        value = closes[-1] / closes[-window - 1] - 1 if len(closes) > window else None
        if value is not None and not math.isfinite(value):
            raise ValueError("Momentum exceeds finite numeric limits")
        return value
    if aligned is not None and external_name in aligned[i]:
        value = aligned[i][external_name]
        if value is not None and (not isinstance(value, (int, float)) or not math.isfinite(value)):
            raise ValueError("Aligned rule features must be finite numbers or missing")
        return value
    external_field = name[6:] if name.startswith("event:") else name
    if name == "temperature" or any(event.field == external_field for event in events):
        # At close time of this bar. Interval duration is explicit, never inferred from future data.
        when = bars[i].timestamp + timedelta(
            seconds=spec.get("bar_seconds", 86400),
            microseconds=math.ceil(float(spec.get("data_delay_ms", 0)) * 1000),
        )
        return available_value(
            events,
            when,
            field=external_field,
            location=spec.get("location"),
            max_age_hours=spec.get("event_max_age_hours", 48),
        )
    raise ValueError(f"Unsupported feature: {name}")


def evaluate_rule(
    rule: dict, bars: list[Bar], i: int, events: list[Event], spec: dict, depth: int = 0
) -> bool:
    if depth > 8:
        raise ValueError("Rule nesting exceeds eight levels")
    for group in ("all", "any"):
        if group in rule:
            children = rule[group]
            if not isinstance(children, list) or not 1 <= len(children) <= 20:
                raise ValueError("AND/OR groups need 1..20 conditions")
            results = [evaluate_rule(r, bars, i, events, spec, depth + 1) for r in children]
            return all(results) if group == "all" else any(results)
    left = feature(str(rule["left"]), bars, i, events, spec)
    right = (
        feature(rule["right"], bars, i, events, spec)
        if isinstance(rule["right"], str)
        else float(rule["right"])
    )
    if right is not None and not math.isfinite(right):
        raise ValueError("Rule threshold must be finite")
    op = rule.get("op")
    if op not in {">", "<", ">=", "<=", "=="}:
        raise ValueError("Rule comparison must be >, <, >=, <= or ==")
    if left is None or right is None:
        return False
    return {
        ">": left > right,
        "<": left < right,
        ">=": left >= right,
        "<=": left <= right,
        "==": left == right,
    }[op]


def preset(
    name: str = "sma_cross",
    *,
    fast: int = 20,
    slow: int = 50,
    amount: float = 100,
    threshold: float = 5,
) -> dict:
    if not 1 <= fast <= 1000 or not 1 <= slow <= 1000:
        raise ValueError("Indicator windows must be 1..1000")
    base = {
        "name": name,
        "bar_seconds": 86400,
        "event_max_age_hours": 48,
        "sizing": "target",
        "weight": 1.0,
    }
    if name == "buy_hold":
        base["entry"] = {"left": "close", "op": ">", "right": 0}
        base["once"] = True
    elif name == "sma_cross":
        base["entry"] = {"left": f"sma_{fast}", "op": ">", "right": f"sma_{slow}"}
        base["exit"] = {"left": f"sma_{fast}", "op": "<=", "right": f"sma_{slow}"}
    elif name == "momentum":
        base["entry"] = {"left": f"momentum_{fast}", "op": ">", "right": 0}
        base["exit"] = {"left": f"momentum_{fast}", "op": "<=", "right": 0}
    elif name == "mean_reversion":
        base["entry"] = {"left": f"momentum_{fast}", "op": "<", "right": -0.02}
        base["exit"] = {"left": f"momentum_{fast}", "op": ">=", "right": 0}
    elif name == "weather":
        base.update(
            sizing="cash",
            amount=amount,
            entry={
                "all": [
                    {"left": "temperature", "op": "<", "right": threshold},
                    {"left": "close", "op": ">", "right": f"sma_{slow}"},
                ]
            },
        )
    elif name in {"ice_cream", "merch", "rubber_ducks", "traffic"}:
        field, default = {
            "ice_cream": ("ice_cream_sales", 120),
            "merch": ("merch_sales", 65),
            "rubber_ducks": ("rubber_duck_sales", 30),
            "traffic": ("traffic_count", 1400),
        }[name]
        base.update(
            sizing="cash",
            amount=amount,
            entry={
                "all": [
                    {"left": f"event:{field}", "op": ">", "right": default},
                    {"left": "close", "op": ">", "right": f"sma_{fast}"},
                ]
            },
        )
    else:
        raise ValueError(
            "Choose a supported preset or compose conditions over any imported event field"
        )
    return base


def parse_hypothesis(text: str, fields: list[str] | None = None) -> dict:
    """Full-match a small public grammar. Never invent a partial interpretation."""
    value = text.strip().lower().rstrip(".")
    field_aliases = {}
    for field in sorted(fields or [], key=len, reverse=True):
        if not isinstance(field, str):
            raise ValueError("Mapped field names must be strings")
        normalized = re.sub(r"[^a-z0-9_.:-]", "_", field.casefold())
        if not normalized or not normalized[0].isalpha():
            continue
        field_aliases[normalized] = field
        for alias in {field.casefold(), field.casefold().replace("_", " ")}:
            value = re.sub(
                r"(?<!\w)" + re.escape(alias) + r"(?!\w)", lambda match: normalized, value
            )
    if value in {"buy and hold bitcoin", "buy and hold btc"}:
        return preset("buy_hold")
    match = re.fullmatch(
        r"buy \$(\d+(?:\.\d+)?) of (?:bitcoin|btc) whenever (?:the )?temperature (?:in this town )?(?:falls|drops) below (-?\d+(?:\.\d+)?)\s*(?:°c|c),? (?:provided|when) (?:bitcoin|btc) is above (?:its |the )?(\d+)-day moving average",
        value,
    )
    if match:
        amount, threshold, slow = match.groups()
        if float(amount) <= 0:
            raise ValueError("Buy amount must be positive")
        return preset("weather", slow=int(slow), amount=float(amount), threshold=float(threshold))
    match = re.fullmatch(r"buy (?:bitcoin|btc) when (\d+)-day sma is above (\d+)-day sma", value)
    if match:
        return preset("sma_cross", fast=int(match[1]), slow=int(match[2]))
    match = re.fullmatch(
        r"buy \$(\d+(?:\.\d+)?) when ([a-z][a-z0-9_.:-]*) (>|<|>=|<=|is above|is below) (-?\d+(?:\.\d+)?)",
        value,
    )
    if match:
        amount, field, comparison, level = match.groups()
        field = field_aliases.get(field, field)
        return {
            "name": "custom_rules",
            "bar_seconds": 86400,
            "sizing": "cash",
            "amount": float(amount),
            "entry": {
                "left": f"event:{field}" if not field.startswith("event:") else field,
                "op": {"is above": ">", "is below": "<"}.get(comparison, comparison),
                "right": float(level),
            },
        }
    raise ValueError(
        "This sentence is outside the supported grammar. Choose a guided template or edit the rule tree; no rules were guessed."
    )


def decisions_for(
    bars: list[Bar],
    spec: dict,
    events: list[Event] | None = None,
    *,
    start_index: int = 0,
    end_index: int | None = None,
) -> list[Decision | None]:
    end = len(bars) if end_index is None else end_index
    if (
        isinstance(start_index, bool)
        or not isinstance(start_index, int)
        or isinstance(end, bool)
        or not isinstance(end, int)
        or not 0 <= start_index < end <= len(bars)
    ):
        raise ValueError("Rule evaluation bounds must use an inclusive start and exclusive end")
    duration = float(spec.get("bar_seconds", 86400))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("bar_seconds must be positive")
    data_delay = float(spec.get("data_delay_ms", 0))
    if not math.isfinite(data_delay) or not 0 <= data_delay <= 31_536_000_000:
        raise ValueError("data_delay_ms must be between zero and 365 days")
    if any((b.timestamp - a.timestamp).total_seconds() < duration for a, b in zip(bars, bars[1:])):
        raise ValueError("bar_seconds overlaps the next bar; set the actual market interval")
    locations_by_field: dict[str, set[str]] = {}
    for event in events or []:
        locations_by_field.setdefault(event.field, set()).add(event.location)
    if any(len(locations) > 1 for locations in locations_by_field.values()) and not spec.get(
        "location"
    ):
        raise ValueError("Select a location when an event field contains multiple locations")
    result: list[Decision | None] = []
    entered = False
    for i in range(len(bars)):
        if i < start_index or i >= end:
            result.append(None)
            continue
        ready = (
            bars[i].timestamp
            + timedelta(seconds=duration, microseconds=math.ceil(data_delay * 1000))
            if data_delay
            else None
        )
        if spec.get("exit") and evaluate_rule(spec["exit"], bars, i, events or [], spec):
            result.append(Decision(target_weight=0, available_at=ready))
        elif not (spec.get("once") and entered) and evaluate_rule(
            spec["entry"], bars, i, events or [], spec
        ):
            result.append(
                Decision(buy_cash=float(spec.get("amount", 100)), available_at=ready)
                if spec.get("sizing") == "cash"
                else Decision(target_weight=float(spec.get("weight", 1)), available_at=ready)
            )
            entered = True
        else:
            result.append(None)
    return result


def python_decisions(bars: list[Bar], strategy: Strategy) -> list[Decision | None]:
    return [strategy.decide(tuple(bars[: i + 1])) for i in range(len(bars))]
