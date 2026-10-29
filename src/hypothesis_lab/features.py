"""Domain-independent CSV/JSON observations and causal, availability-aware features."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .data import Bar, Event, timestamp, validate_bars

MAX_ROWS = 20000
MAX_COLUMNS = 100
HASH_BUCKETS = 8


def _flatten(value: dict, prefix: str = "", depth: int = 0) -> dict:
    if depth > 5:
        raise ValueError("Nested JSON exceeds five levels; flatten or select a smaller record")
    result: dict[str, Any] = {}
    for key, item in value.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        if not name or len(name) > 128 or "\x00" in name:
            raise ValueError("Column names must be nonempty and at most 128 characters")
        if isinstance(item, dict):
            nested = _flatten(item, name, depth + 1)
            if set(result).intersection(nested):
                raise ValueError("Nested JSON column names collide after flattening")
            result.update(nested)
        elif isinstance(item, list):
            if len(item) > 16 or any(isinstance(v, (dict, list)) for v in item):
                raise ValueError("Use precomputed numeric features for nested/large arrays")
            nested = {f"{name}.{i}": v for i, v in enumerate(item)}
            if set(result).intersection(nested):
                raise ValueError("Array feature names collide after flattening")
            result.update(nested)
        else:
            if name in result:
                raise ValueError("JSON feature names collide after flattening")
            result[name] = item
    if len(result) > MAX_COLUMNS:
        raise ValueError("Use at most 100 flattened columns")
    return result


def read_records(content: str, format_name: str = "csv") -> list[dict[str, Any]]:
    if not isinstance(content, str) or not content.strip() or len(content.encode()) > 4_000_000:
        raise ValueError("Choose a nonempty CSV/JSON table under 4 MB")
    if format_name == "csv":
        csv.field_size_limit(4_000_000)
        reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")))
        if (
            not reader.fieldnames
            or any(not name.strip() for name in reader.fieldnames)
            or len(reader.fieldnames) != len(set(reader.fieldnames))
        ):
            raise ValueError("CSV requires distinct named columns")
        rows = []
        for item in reader:
            if None in item:
                raise ValueError("CSV contains more values than header columns")
            rows.append(item)
            if len(rows) > MAX_ROWS:
                raise ValueError("Use at most 20,000 observations")
    elif format_name == "json":

        def invalid(value):
            raise ValueError("JSON cannot contain NaN or infinity")

        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("JSON object keys must be distinct")
                result[key] = value
            return result

        raw = json.loads(content, parse_constant=invalid, object_pairs_hook=unique_object)
        if isinstance(raw, dict):
            raw = next(
                (raw[k] for k in ("records", "data", "items") if isinstance(raw.get(k), list)), None
            )
        if not isinstance(raw, list) or any(not isinstance(row, dict) for row in raw):
            raise ValueError(
                "JSON must be an array of records or an object containing records/data/items"
            )
        if not 1 <= len(raw) <= MAX_ROWS:
            raise ValueError("Use one to 20,000 observations")
        rows = [_flatten(row) for row in raw]
    else:
        raise ValueError("Supported tabular input formats are csv and json")
    columns = {key for row in rows for key in row}
    if not rows or not 1 <= len(columns) <= MAX_COLUMNS:
        raise ValueError("Use a nonempty table with at most 100 columns")
    return rows


def _numeric(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return float(value)
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(number):
        raise ValueError("Numeric feature values must be finite")
    return number


def inspect_dataset(content: str, format_name: str = "csv", mapping: dict | None = None) -> dict:
    rows = read_records(content, format_name)
    columns = list(dict.fromkeys(key for row in rows for key in row))
    config = dict(mapping or {})
    observed = config.get("observed_at_column", config.get("timestamp_column"))
    if observed is None:
        observed = next(
            (
                name
                for name in ("observed_at", "timestamp", "date", "time", "datetime")
                if name in columns
            ),
            "",
        )
    available = config.get(
        "available_at_column",
        next(
            (name for name in ("available_at", "published_at", "release_time") if name in columns),
            "",
        ),
    )
    mode = config.get("availability_mode", "column" if available else "acquired")
    if mode not in {"column", "lag", "acquired"}:
        raise ValueError("Availability mode must be column, lag or acquired")
    numeric, categories = [], []
    ignored = {observed, available}
    long_field = config.get("series_column")
    long_value = config.get("value_column")
    if not long_field and {"field", "value"}.issubset(columns):
        long_field, long_value = "field", "value"
    if long_field:
        if long_field not in columns or long_value not in columns:
            raise ValueError("Select valid long-format field and value columns")
        numeric = list(dict.fromkeys(str(row[long_field]) for row in rows))
        if any(not name.strip() or len(name) > 128 or "\x00" in name for name in numeric):
            raise ValueError("Long-format series names must be nonempty and at most 128 characters")
        if len(numeric) > 32:
            raise ValueError("Select at most 32 long-format series")
    else:
        for name in columns:
            if name in ignored:
                continue
            nonempty = [
                row.get(name) for row in rows if row.get(name) is not None and row.get(name) != ""
            ]
            if not nonempty:
                continue
            if all(_numeric(value) is not None for value in nonempty):
                numeric.append(name)
            else:
                categories.append(name)
    fields = config.get("field_columns", numeric[:8])
    categorical = config.get("categorical_columns", [])
    if not isinstance(fields, list) or not isinstance(categorical, list):
        raise ValueError("Select at least one numeric, categorical or text-derived feature")
    if any(name not in numeric for name in fields) or any(
        name not in categories for name in categorical
    ):
        raise ValueError("Selected feature columns do not match the inspected types")
    if len(set(fields + categorical)) != len(fields + categorical):
        raise ValueError("Feature columns must be distinct")
    text_features = config.get("text_features", [])
    if not isinstance(text_features, list) or len(text_features) > 8:
        raise ValueError("Use at most eight explicit text feature definitions")
    for item in text_features:
        if (
            not isinstance(item, dict)
            or item.get("column") not in categories
            or item.get("operation") not in {"count", "contains", "length"}
            or not isinstance(item.get("name"), str)
            or not item.get("name", "").strip()
        ):
            raise ValueError(
                "Text features require a text column, name and count/contains/length operation"
            )
        if item["operation"] != "length" and not str(item.get("needle", "")):
            raise ValueError("Choose a nonempty phrase to count or match")
    generated = (
        fields
        + [f"{name}__hash_{bucket}" for name in categorical for bucket in range(HASH_BUCKETS)]
        + [item["name"] for item in text_features]
    )
    if len(generated) != len(set(generated)):
        raise ValueError("Encoded feature names must be distinct")
    if len(generated) > 32 or any(name.startswith("market.") for name in generated):
        raise ValueError("Select at most 32 encoded features; market.* is a reserved namespace")
    config.update(
        observed_at_column=observed,
        timestamp_column=observed,
        available_at_column=available,
        availability_mode=mode,
        field_columns=fields,
        categorical_columns=categorical,
        acquired_at=(config.get("acquired_at") or datetime.now(UTC).isoformat())
        if mode == "acquired"
        else config.get("acquired_at"),
        max_age_hours=float(config.get("max_age_hours", 48)),
        timezone=config.get("timezone", ""),
    )
    if long_field:
        config.update(series_column=long_field, value_column=long_value)
    warnings = []
    if not observed:
        warnings.append("Choose an observation timestamp column before running the experiment.")
    if mode == "acquired":
        warnings.append(
            "Publication times are unknown: availability defaults to acquisition time. Values cannot trigger earlier historical trades."
        )
    if mode == "lag":
        lag = float(config.get("availability_lag_hours", 24))
        if not math.isfinite(lag) or not 0 <= lag <= 87600:
            raise ValueError("Assumed publication lag must be 0..87,600 hours")
        config["availability_lag_hours"] = lag
        warnings.append(
            f"Exploratory assumption: values become available {lag:g} hours after observation. This is not verified point-in-time publication history."
        )
    if not math.isfinite(config["max_age_hours"]) or config["max_age_hours"] <= 0:
        raise ValueError("Feature expiry must be positive and finite")
    if categorical:
        warnings.append(
            "Categorical inputs use eight fixed SHA-256 buckets per field. No future vocabulary is learned; collisions are possible."
        )
    return {
        "format": format_name,
        "columns": columns,
        "numeric_fields": numeric,
        "categorical_fields": categories,
        "rows": len(rows),
        "preview": [
            {key: value[:500] if isinstance(value, str) else value for key, value in row.items()}
            for row in rows[:8]
        ],
        "mapping": config,
        "generated_fields": generated,
        "warnings": warnings,
    }


def _time(value: Any, configured_timezone: str, format_name: str = "iso") -> datetime:
    if not isinstance(format_name, str):
        raise ValueError("Timestamp format must be iso, unix_seconds or unix_milliseconds")
    if format_name in {"unix_seconds", "unix_milliseconds"}:
        try:
            number = float(value)
            if isinstance(value, bool) or not math.isfinite(number):
                raise ValueError()
            return datetime.fromtimestamp(
                number / (1000 if format_name == "unix_milliseconds" else 1), UTC
            )
        except (TypeError, ValueError, OverflowError, OSError):
            raise ValueError("Invalid timestamp for the explicitly chosen Unix time unit") from None
    if format_name != "iso":
        raise ValueError("Timestamp format must be iso, unix_seconds or unix_milliseconds")
    if not isinstance(value, str):
        raise ValueError(
            "Observation/availability timestamps must be ISO strings; convert Unix timestamps explicitly"
        )
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        if configured_timezone == "UTC":
            stamp = stamp.replace(tzinfo=UTC)
        elif isinstance(configured_timezone, str) and re.fullmatch(
            r"[+-]\d{2}:\d{2}", configured_timezone
        ):
            sign = 1 if configured_timezone[0] == "+" else -1
            hours, minutes = map(int, configured_timezone[1:].split(":"))
            if hours > 23 or minutes > 59:
                raise ValueError("Invalid UTC offset")
            stamp = stamp.replace(tzinfo=timezone(sign * timedelta(hours=hours, minutes=minutes)))
        else:
            raise ValueError(
                "Naive/date-only input needs an explicit timezone mapping, such as UTC"
            )
    return timestamp(stamp)


@dataclass(frozen=True)
class Observation:
    observed_at: datetime
    available_at: datetime
    values: dict[str, float | None]


def prepare_dataset(
    content: str, format_name: str = "csv", mapping: dict | None = None
) -> tuple[list[Observation], dict]:
    info = inspect_dataset(content, format_name, mapping)
    config = info["mapping"]
    if not info["generated_fields"]:
        raise ValueError("Select at least one numeric, categorical or text-derived feature")
    if not config["observed_at_column"]:
        raise ValueError("Choose an observation timestamp column")
    if config["availability_mode"] == "column" and not config["available_at_column"]:
        raise ValueError("Choose a publication/availability column")
    rows = read_records(content, format_name)
    observations, keys = [], set()
    for row in rows:
        observed = _time(
            row[config["observed_at_column"]],
            config["timezone"],
            config.get("timestamp_format", "iso"),
        )
        if config["availability_mode"] == "column":
            available = _time(
                row[config["available_at_column"]],
                config["timezone"],
                config.get("available_at_format", "iso"),
            )
        elif config["availability_mode"] == "lag":
            available = observed + timedelta(hours=config["availability_lag_hours"])
        else:
            available = timestamp(config["acquired_at"])
        if available < observed:
            raise ValueError("An observation cannot be available before it was observed")
        if config.get("series_column"):
            name = str(row[config["series_column"]])
            values = (
                {name: _numeric(row.get(config["value_column"]))}
                if name in config["field_columns"]
                else {}
            )
        else:
            values = {name: _numeric(row.get(name)) for name in config["field_columns"]}
            for name in config["categorical_columns"]:
                raw = row.get(name)
                bucket = (
                    None
                    if raw is None or raw == ""
                    else int.from_bytes(hashlib.sha256(str(raw).encode()).digest()[:4], "big")
                    % HASH_BUCKETS
                )
                values.update(
                    {
                        f"{name}__hash_{i}": None if bucket is None else float(i == bucket)
                        for i in range(HASH_BUCKETS)
                    }
                )
            for item in config.get("text_features", []):
                raw = row.get(item["column"])
                text = "" if raw is None else str(raw).casefold()
                needle = str(item.get("needle", "")).casefold()
                values[item["name"]] = (
                    None
                    if raw is None
                    else float(
                        len(text)
                        if item["operation"] == "length"
                        else text.count(needle)
                        if item["operation"] == "count"
                        else needle in text
                    )
                )
        if not values:
            continue
        key = (observed, available, tuple(sorted(values)))
        if key in keys:
            raise ValueError(
                "Duplicate observation/revision keys are ambiguous; aggregate or disambiguate first"
            )
        keys.add(key)
        observations.append(Observation(observed, available, values))
    return sorted(observations, key=lambda r: r.available_at), info


def align_features(
    bars: list[Bar], observations: list[Observation], info: dict, bar_seconds: float = 86400
) -> list[dict[str, float | None]]:
    """Linear sweep of publications, retaining the latest known revision by observation time."""
    fields = info["generated_fields"]
    age = info["mapping"]["max_age_hours"] * 3600
    published: dict[str, tuple[datetime, datetime, float | None]] = {}
    cursor, result = 0, []
    for index, bar in enumerate(bars):
        when = bar.timestamp + timedelta(seconds=bar_seconds)
        while cursor < len(observations) and observations[cursor].available_at <= when:
            item = observations[cursor]
            for name, value in item.values.items():
                old = published.get(name)
                if old is None or (item.observed_at, item.available_at) > old[:2]:
                    published[name] = (item.observed_at, item.available_at, value)
            cursor += 1
        row = {
            name: None
            if name not in published or (when - published[name][0]).total_seconds() > age
            else published[name][2]
            for name in fields
        }
        row.update(
            {
                "market.close": bar.close,
                "market.volume": bar.volume,
                "market.return_1": bar.close / bars[index - 1].close - 1 if index else None,
            }
        )
        result.append(row)
    return result


def as_events(observations: list[Observation]) -> list[Event]:
    return [
        Event(item.observed_at, item.available_at, value, field, "Feature table")
        for item in observations
        for field, value in item.values.items()
        if value is not None
    ]


def demo_content() -> str:
    return (Path(__file__).with_name("fixtures") / "world_signals.csv").read_text(encoding="utf-8")


def market_from_dataset(content: str, format_name: str, mapping: dict) -> dict:
    """Normalize a user API/CSV/JSON OHLCV table without fabricating missing prices."""
    if not isinstance(mapping, dict):
        raise ValueError("Market column mapping must be an object")
    rows = read_records(content, format_name)
    if len(rows) > 5000:
        raise ValueError("Choose at most 5,000 market bars for the interactive workbench")
    time_column = mapping.get("timestamp_column", mapping.get("observed_at_column", "timestamp"))
    fields = {name: mapping.get(name, name) for name in ("open", "high", "low", "close", "volume")}
    required = [time_column, *(fields[name] for name in ("open", "high", "low", "close"))]
    if any(not isinstance(name, str) or not name for name in required):
        raise ValueError("Map a timestamp and actual open/high/low/close columns")
    if not isinstance(fields["volume"], str):
        raise ValueError("Map a volume column or leave it blank when unavailable")
    if "volume" in mapping and fields["volume"]:
        required.append(fields["volume"])
    if any(name not in row for row in rows for name in required):
        raise ValueError(
            "Selected market columns must be present in every row; prices are never invented"
        )
    bars = []
    try:
        for row in rows:
            bars.append(
                Bar(
                    _time(
                        row[time_column],
                        mapping.get("timezone", ""),
                        mapping.get("timestamp_format", "iso"),
                    ),
                    float(row[fields["open"]]),
                    float(row[fields["high"]]),
                    float(row[fields["low"]]),
                    float(row[fields["close"]]),
                    float(row.get(fields["volume"]) or 0),
                )
            )
    except (KeyError, TypeError, OverflowError):
        raise ValueError(
            "Required market columns are absent or nonnumeric; prices are never invented"
        ) from None
    validate_bars(bars)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
    writer.writerows(
        [bar.timestamp.isoformat(), bar.open, bar.high, bar.low, bar.close, bar.volume]
        for bar in bars
    )
    return {
        "market_csv": output.getvalue(),
        "rows": len(bars),
        "start": bars[0].timestamp.isoformat(),
        "end": bars[-1].timestamp.isoformat(),
        "warnings": [
            "Imported market rows must be completed intervals. Set the actual bar duration and quote-currency assumptions before running. Corporate-action and survivorship adjustments remain the source owner's responsibility."
        ],
    }


def derive_features(
    rows: list[dict[str, float | None]], transforms: list[dict] | None = None
) -> list[dict[str, float | None]]:
    """Explicit trailing transforms; no Python expressions or future fitting."""
    result = [dict(row) for row in rows]
    if not transforms:
        return result
    if not isinstance(transforms, list) or len(transforms) > 16:
        raise ValueError("Use at most sixteen feature transformations")
    for item in transforms:
        if not isinstance(item, dict):
            raise ValueError("Every feature transformation must be an object")
        source, name = item.get("source"), item.get("name")
        operation = item.get("operation")
        raw_window = item.get("window", 1)
        try:
            number = float(raw_window)
            if isinstance(raw_window, bool) or not math.isfinite(number) or not number.is_integer():
                raise ValueError()
            window = int(number)
        except (ValueError, TypeError, OverflowError):
            raise ValueError("Transform window must be an integer from 1 to 1000") from None
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(source, str)
            or not 1 <= window <= 1000
        ):
            raise ValueError("Transforms need source/name strings and a 1..1000 bar window")
        if any(name in row for row in result) or not any(source in row for row in result):
            raise ValueError("Transform output must be new and source must exist")
        if operation not in {"lag", "difference", "pct_change", "mean", "sum", "zscore"}:
            raise ValueError("Use lag, difference, pct_change, mean, sum or zscore")
        for index, row in enumerate(result):
            current = row.get(source)
            value = None
            if operation in {"lag", "difference", "pct_change"} and index >= window:
                previous = result[index - window].get(source)
                if previous is not None:
                    value = (
                        previous
                        if operation == "lag"
                        else None
                        if current is None
                        else current - previous
                        if operation == "difference"
                        else current / previous - 1
                        if previous != 0
                        else None
                    )
            elif operation in {"mean", "sum", "zscore"} and index + 1 >= window:
                values = [item.get(source) for item in result[index + 1 - window : index + 1]]
                if all(v is not None for v in values):
                    numbers = [float(v) for v in values if v is not None]
                    mean = sum(numbers) / window
                    variance = sum((v - mean) ** 2 for v in numbers) / window
                    value = (
                        sum(numbers)
                        if operation == "sum"
                        else mean
                        if operation == "mean"
                        else (current - mean) / math.sqrt(variance)
                        if current is not None and variance > 0
                        else 0.0
                    )
            row[name] = value
    return result


def idea_examples() -> list[dict]:
    return [
        {
            "id": "ice_cream",
            "title": "Ice cream vs. the market",
            "question": "Buy $100 when ice_cream_sales exceeds 120 and price is above its 20-bar average.",
            "field": "ice_cream_sales",
            "threshold": 120,
            "target": "ice_cream_sales",
        },
        {
            "id": "merch",
            "title": "A merch drop as a signal",
            "question": "Buy when a model assigns more than 0.5 probability that merch_sales will increase.",
            "field": "merch_sales",
            "threshold": 65,
            "target": "merch_sales",
        },
        {
            "id": "traffic",
            "title": "Rush-hour hypothesis",
            "question": "Investigate whether traffic_count predicts market returns after costs.",
            "field": "traffic_count",
            "threshold": 1400,
            "target": "traffic_count",
        },
        {
            "id": "urban",
            "title": "A growing city",
            "question": "Compare urban_growth_index with prices, while respecting slower publication and revisions.",
            "field": "urban_growth_index",
            "threshold": 102,
            "target": "urban_growth_index",
        },
        {
            "id": "shipping",
            "title": "Ships and probabilities",
            "question": "If probability of shipping_volume rising is greater than 0.5, buy; otherwise hold or exit.",
            "field": "shipping_volume",
            "threshold": 80,
            "target": "shipping_volume",
        },
        {
            "id": "weird",
            "title": "Rubber ducks and moon phases",
            "question": "Combine rubber_duck_sales, moon_phase and an explicit trading rule. Then inspect when it fails.",
            "field": "rubber_duck_sales",
            "threshold": 30,
            "target": "rubber_duck_sales",
        },
    ]
