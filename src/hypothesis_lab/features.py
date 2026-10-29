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
    if format_name in {"csv", "tsv"}:
        csv.field_size_limit(4_000_000)
        reader = csv.DictReader(
            io.StringIO(content.lstrip("\ufeff")), delimiter="\t" if format_name == "tsv" else ","
        )
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
    elif format_name in {"json", "ndjson", "geojson"}:

        def invalid(value):
            raise ValueError("JSON cannot contain NaN or infinity")

        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("JSON object keys must be distinct")
                result[key] = value
            return result

        if format_name == "ndjson":
            lines = [line for line in content.splitlines() if line.strip()]
            if len(lines) > MAX_ROWS:
                raise ValueError("Use at most 20,000 observations")
            raw = [
                json.loads(line, parse_constant=invalid, object_pairs_hook=unique_object)
                for line in lines
            ]
        else:
            raw = json.loads(content, parse_constant=invalid, object_pairs_hook=unique_object)
        if isinstance(raw, dict) and raw.get("type") == "FeatureCollection":
            features = raw.get("features")
            if not isinstance(features, list) or not 1 <= len(features) <= MAX_ROWS:
                raise ValueError("GeoJSON requires one to 20,000 features")
            records = []
            for feature in features:
                if (
                    not isinstance(feature, dict)
                    or feature.get("type") != "Feature"
                    or not isinstance(feature.get("properties"), dict)
                ):
                    raise ValueError("GeoJSON features need an object of properties")
                row = dict(feature["properties"])
                if any(name in row for name in ("_geometry_type", "_longitude", "_latitude")):
                    raise ValueError("GeoJSON properties collide with reserved geometry columns")
                geometry = feature.get("geometry")
                if geometry is not None:
                    if not isinstance(geometry, dict) or not isinstance(geometry.get("type"), str):
                        raise ValueError("Invalid GeoJSON geometry")
                    row["_geometry_type"] = geometry["type"]
                    if geometry["type"] == "Point":
                        coordinates = geometry.get("coordinates")
                        if (
                            not isinstance(coordinates, list)
                            or len(coordinates) not in {2, 3}
                            or any(
                                isinstance(v, bool)
                                or not isinstance(v, (int, float))
                                or not math.isfinite(v)
                                for v in coordinates
                            )
                        ):
                            raise ValueError(
                                "GeoJSON Point coordinates must be finite numeric longitude/latitude"
                            )
                        if not -180 <= coordinates[0] <= 180 or not -90 <= coordinates[1] <= 90:
                            raise ValueError("GeoJSON Point longitude/latitude are out of range")
                        row.update(_longitude=coordinates[0], _latitude=coordinates[1])
                records.append(row)
            raw = records
        elif format_name == "geojson":
            raise ValueError("GeoJSON import requires a FeatureCollection")
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
        raise ValueError(
            "Supported inputs are csv, tsv, json, ndjson and GeoJSON FeatureCollection; binary/raster formats need an explicit external extraction"
        )
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


DATE_FORMATS = {
    "date_dmy": ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %b %Y", "%d-%b-%Y"),
    "date_mdy": ("%m/%d/%Y", "%m-%d-%Y", "%b %d, %Y"),
    "yyyymmdd": ("%Y%m%d",),
    "year": ("%Y",),
    "year_month": ("%Y-%m", "%Y/%m"),
}


def _date_parse(value: str, format_name: str) -> datetime:
    for pattern in DATE_FORMATS[format_name]:
        try:
            return datetime.strptime(value, pattern)
        except ValueError:
            pass
    raise ValueError(f"Date does not match the selected {format_name} format")


def _time_candidates(rows: list[dict], columns: list[str]) -> list[dict]:
    result = []
    for name in columns:
        sample = [row[name] for row in rows[:200] if row.get(name) not in (None, "")]
        if not sample:
            continue
        hint = bool(
            re.search(r"date|time|year|month|epoch|observ|publish|release|acquir", name, re.I)
        )
        formats = []
        if all(isinstance(v, str) and len(v) >= 10 for v in sample):
            try:
                for value in sample:
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                formats.append("iso")
            except ValueError:
                pass
        if hint or all(isinstance(v, str) and bool(re.search(r"[/.-]", v)) for v in sample):
            for format_name in DATE_FORMATS:
                try:
                    for value in sample:
                        _date_parse(str(value), format_name)
                    formats.append(format_name)
                except ValueError:
                    pass
        if hint and not formats:
            for format_name, divisor in (("unix_seconds", 1), ("unix_milliseconds", 1000)):
                try:
                    years = [datetime.fromtimestamp(float(v) / divisor, UTC).year for v in sample]
                    if all(not isinstance(v, bool) for v in sample) and all(
                        1990 <= year <= 2100 for year in years
                    ):
                        formats.append(format_name)
                except (ValueError, TypeError, OverflowError, OSError):
                    pass
        if formats:
            result.append(
                {
                    "column": name,
                    "formats": formats,
                    "ambiguous": len(formats) > 1,
                    "reason": "Matches sampled values; verify units, timezone and period boundary.",
                }
            )
    return result


def _parts(mapping: dict, name: str, columns: list[str]) -> dict:
    value = mapping.get(name, {})
    if not isinstance(value, dict) or (
        value and ("year" not in value or set(value) - {"year", "month", "day"})
    ):
        raise ValueError("Composite time parts require year and optional month/day column names")
    if "day" in value and "month" not in value:
        raise ValueError("Composite day requires a month column")
    if any(not isinstance(column, str) or column not in columns for column in value.values()):
        raise ValueError("Composite time parts must name existing columns")
    return value


def _row_time(row: dict, mapping: dict, available: bool = False) -> datetime:
    prefix = "available_at" if available else "timestamp"
    parts = mapping.get(prefix + "_parts", {})
    coarse = ""
    if parts:
        components = {}
        for part, column in parts.items():
            raw = row.get(column)
            if part == "month" and isinstance(raw, str):
                month_names = "january february march april may june july august september october november december".split()
                normalized = raw.strip().casefold().rstrip(".")
                raw = next(
                    (
                        i
                        for i, name in enumerate(month_names, 1)
                        if normalized in {name, name[:3]}
                        or (name == "september" and normalized == "sept")
                    ),
                    raw,
                )
            try:
                if raw is None:
                    raise ValueError()
                number = float(raw)
                if isinstance(raw, bool) or not math.isfinite(number) or not number.is_integer():
                    raise ValueError()
                components[part] = int(number)
            except (ValueError, TypeError, OverflowError):
                raise ValueError(
                    "Calendar parts need integer year/day and a numeric or English month name"
                ) from None
        value = datetime(
            components["year"], components.get("month", 1), components.get("day", 1)
        ).isoformat()
        stamp = _time(value, mapping.get("timezone", ""))
        coarse = "year" if "month" not in parts else "month" if "day" not in parts else ""
    else:
        column = mapping.get(
            "available_at_column" if available else "observed_at_column",
            mapping.get("timestamp_column", "timestamp"),
        )
        if column not in row:
            raise ValueError("The selected timestamp column is missing from a row")
        format_name = mapping.get("available_at_format" if available else "timestamp_format", "iso")
        stamp = _time(row[column], mapping.get("timezone", ""), format_name)
        coarse = "year" if format_name == "year" else "month" if format_name == "year_month" else ""
    if coarse and mapping.get("period_boundary", "end") == "end":
        # Complete the local calendar period before normalizing to UTC.
        zone = mapping.get("timezone", "")
        offset = timedelta()
        if isinstance(zone, str) and re.fullmatch(r"[+-]\d{2}:\d{2}", zone):
            hours, minutes = map(int, zone[1:].split(":"))
            offset = (1 if zone[0] == "+" else -1) * timedelta(hours=hours, minutes=minutes)
        local = stamp + offset
        next_month = 1 if coarse == "year" or local.month == 12 else local.month + 1
        next_year = local.year + (coarse == "year" or local.month == 12)
        stamp = _time(datetime(next_year, next_month, 1).isoformat(), zone)
    return stamp


def _entities(rows: list[dict], columns: list[str]) -> list[dict]:
    result = []
    for column in columns:
        if not re.search(
            r"(^|[_. ])(country|state|city|region|entity|station|airport|store|shop|product|sku|port|location|site|symbol|ticker|name|object|satellite)([_. ]|$)|^(country|state|city|entity|station|airport|store|shop|product|sku|port|location|site|symbol|ticker|object|satellite)_?(id|name|code)?$",
            column,
            re.I,
        ):
            continue
        values = list(
            dict.fromkeys(
                row.get(column)
                for row in rows
                if isinstance(row.get(column), (str, int, float)) and row.get(column) != ""
            )
        )
        if 1 < len(values) <= 1000:
            result.append(
                {
                    "column": column,
                    "values": values[:50],
                    "count": len(values),
                    "truncated": len(values) > 50,
                }
            )
    return result


def inspect_dataset(content: str, format_name: str = "csv", mapping: dict | None = None) -> dict:
    rows = read_records(content, format_name)
    columns = list(dict.fromkeys(key for row in rows for key in row))
    if mapping is not None and not isinstance(mapping, dict):
        raise ValueError("Feature mapping must be an object")
    config = dict(mapping or {})
    time_candidates = _time_candidates(rows, columns)
    issues, assumptions, confirmations = [], [], []
    timestamp_parts = _parts(config, "timestamp_parts", columns)
    available_parts = _parts(config, "available_at_parts", columns)
    observed = config.get("observed_at_column", config.get("timestamp_column"))
    if observed is None:
        observed = next(
            (
                name
                for name in ("observed_at", "timestamp", "date", "time", "datetime")
                if name in columns
            ),
            next((item["column"] for item in time_candidates), ""),
        )
    available = config.get(
        "available_at_column",
        next(
            (name for name in ("available_at", "published_at", "release_time") if name in columns),
            "",
        ),
    )
    if timestamp_parts:
        observed = ""
    mode = config.get("availability_mode", "column" if available or available_parts else "acquired")
    if mode not in {"column", "lag", "acquired"}:
        raise ValueError("Availability mode must be column, lag or acquired")
    numeric, categories = [], []
    entity = config.get("entity_column", "")
    if not isinstance(entity, str) or entity and entity not in columns:
        raise ValueError("Choose an existing entity column")
    selected_filter = config.get("filter")
    if selected_filter is not None:
        if (
            not isinstance(selected_filter, dict)
            or selected_filter.get("column") not in columns
            or "equals" not in selected_filter
            or isinstance(selected_filter["equals"], (dict, list))
        ):
            raise ValueError("Entity filter needs an existing column and one exact equals value")
        entity = selected_filter["column"]
    ignored = {observed, available, entity, *timestamp_parts.values(), *available_parts.values()}
    if observed and "timestamp_format" not in config:
        candidate = next((item for item in time_candidates if item["column"] == observed), None)
        if candidate and len(candidate["formats"]) == 1:
            config["timestamp_format"] = candidate["formats"][0]
            if config["timestamp_format"] != "iso":
                assumptions.append(
                    f"Observation time was recognized as {config['timestamp_format']}; verify this mapping."
                )
    if available and "available_at_format" not in config:
        candidate = next((item for item in time_candidates if item["column"] == available), None)
        if candidate and len(candidate["formats"]) == 1:
            config["available_at_format"] = candidate["formats"][0]
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
    if any(not isinstance(name, str) for name in fields + categorical):
        raise ValueError("Feature selections must be column-name strings")
    removed = [name for name in fields + categorical if isinstance(name, str) and name in ignored]
    if removed:
        assumptions.append(
            "Removed time/entity keys from feature selections: " + ", ".join(dict.fromkeys(removed))
        )
        fields = [name for name in fields if name not in ignored]
        categorical = [name for name in categorical if name not in ignored]
    if any(name not in numeric for name in fields) or any(
        name not in categories for name in categorical
    ):
        raise ValueError("Selected feature columns do not match the inspected types")
    if len(set(fields + categorical)) != len(fields + categorical):
        raise ValueError("Feature columns must be distinct")
    text_features = config.get("text_features", [])
    if not isinstance(text_features, list) or len(text_features) > 8:
        raise ValueError("Use at most eight explicit text feature definitions")
    if any(
        isinstance(item, dict)
        and isinstance(item.get("column"), str)
        and item.get("column") in ignored
        for item in text_features
    ):
        assumptions.append("Removed text transformations that use selected time/entity keys.")
    text_features = [
        item
        for item in text_features
        if not isinstance(item, dict)
        or not isinstance(item.get("column"), str)
        or item.get("column") not in ignored
    ]
    for item in text_features:
        if (
            not isinstance(item, dict)
            or item.get("column") not in categories
            or item.get("operation") not in {"count", "contains", "length", "equals"}
            or not isinstance(item.get("name"), str)
            or not item.get("name", "").strip()
        ):
            raise ValueError(
                "Text features require a text column, name and count/contains/length/equals operation"
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
    if config.get("period_boundary", "end") not in {"start", "end"}:
        raise ValueError("Calendar period boundary must be start or end")
    aggregation = config.get("aggregation")
    if aggregation is not None:
        if (
            not isinstance(aggregation, dict)
            or aggregation.get("frequency") not in {"day", "month"}
            or aggregation.get("operation") not in {"count", "sum", "mean"}
        ):
            raise ValueError("Aggregation needs day/month frequency and count/sum/mean operation")
        selected = aggregation.get("fields", generated)
        if (
            not isinstance(selected, list)
            or any(name not in generated for name in selected)
            or len(set(selected)) != len(selected)
        ):
            raise ValueError("Aggregate fields must be distinct selected feature names")
        if aggregation["operation"] != "count" and not selected:
            raise ValueError(
                "Sum/mean aggregation requires selected numeric or text-derived features"
            )
        aggregation = {**aggregation, "fields": selected}
        generated = (
            ["event_count"]
            if aggregation["operation"] == "count"
            else [
                f"{name}__{aggregation['operation']}_{aggregation['frequency']}"
                for name in selected
            ]
        )
        assumptions.append(
            "Explicit aggregation uses only completed UTC buckets, becomes available after every included row is published, and leaves missing-value sums/means missing. Empty buckets are not invented."
        )
    config.update(
        observed_at_column=observed,
        timestamp_column=observed,
        available_at_column=available,
        availability_mode=mode,
        field_columns=fields,
        categorical_columns=categorical,
        text_features=text_features,
        entity_column=entity,
        timestamp_parts=timestamp_parts,
        available_at_parts=available_parts,
        period_boundary=config.get("period_boundary", "end"),
        acquired_at=(config.get("acquired_at") or datetime.now(UTC).isoformat())
        if mode == "acquired"
        else config.get("acquired_at"),
        max_age_hours=float(config.get("max_age_hours", 48)),
        timezone=config.get("timezone", ""),
    )
    if long_field:
        config.update(series_column=long_field, value_column=long_value)
    if aggregation is not None:
        config["aggregation"] = aggregation
    warnings = list(assumptions)
    if not observed and not timestamp_parts:
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
    entity_candidates = _entities(rows, columns)
    if entity_candidates and not selected_filter and aggregation is None:
        confirmations.append(
            "This table contains several entities. Select one exact entity or explicitly aggregate before combining coincident observations."
        )
    if config.get("timezone", "") == "":
        confirmations.append(
            "Confirm a timezone for date-only, common-format or composite calendar timestamps. No timezone is silently assigned."
        )
    if any(item["ambiguous"] for item in time_candidates):
        issues.append(
            "Some dates are ambiguous between day/month and month/day; choose the format explicitly."
        )
    missing = sum(row.get(name) in (None, "") for row in rows for name in columns)
    duplicate_rows = len(rows) - len(
        {json.dumps(row, sort_keys=True, ensure_ascii=True) for row in rows}
    )
    if missing:
        issues.append(f"{missing} cells are missing; missing values remain missing.")
    if duplicate_rows:
        issues.append(f"{duplicate_rows} duplicate rows; no rows are silently discarded.")
    kind = (
        "long"
        if long_field
        else "entity_panel"
        if entity_candidates
        else "geospatial"
        if "_geometry_type" in columns
        else "time_series"
        if observed or timestamp_parts
        else "static"
    )
    if categories and not numeric:
        kind = "event_log" if observed or timestamp_parts else kind
    if "_geometry_type" in columns:
        assumptions.append(
            "GeoJSON properties are tabular; Point coordinates are exposed as _longitude/_latitude. Polygon/raster geometry is not converted to centroids, areas or satellite passes."
        )
        warnings.append(assumptions[-1])
    suggestions = []
    proposed = {**config, "timezone": config.get("timezone") or "UTC"}
    composite = {
        part: next((name for name in columns if name.casefold() == part), "")
        for part in ("year", "month", "day")
    }
    if composite["year"] and (not observed or config.get("timestamp_format") == "year"):
        proposed.update(
            timestamp_parts={part: name for part, name in composite.items() if name},
            observed_at_column="",
            timestamp_column="",
            period_boundary="end",
        )
    if observed or proposed.get("timestamp_parts"):
        suggestions.append(
            {
                "label": "Use the recognized time and measurements",
                "mapping": proposed,
                "reason": "Review the selected columns and confirm UTC if dates have no zone. Year/month measurements are dated at period completion by default; publication remains independently acquired/column/lag.",
            }
        )
    if observed and categories:
        count_mapping = {
            **proposed,
            "field_columns": [],
            "categorical_columns": [],
            "text_features": [],
            "aggregation": {"frequency": "day", "operation": "count", "fields": []},
        }
        suggestions.append(
            {
                "label": "Count completed daily events",
                "mapping": count_mapping,
                "reason": "Each input row is one event only if you confirm that definition; all entities are counted unless an exact filter is selected.",
            }
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
        "quality": {
            "rows": len(rows),
            "missing_cells": missing,
            "duplicate_rows": duplicate_rows,
            "time_candidates": time_candidates,
            "issues": issues,
        },
        "interpretation": {
            "kind": kind,
            "assumptions": assumptions,
            "requires_confirmation": confirmations,
            "entity_candidates": entity_candidates,
        },
        "suggestions": suggestions,
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
    if format_name != "iso" and format_name not in DATE_FORMATS:
        raise ValueError("Choose ISO, an explicit Unix unit or a supported calendar date format")
    if not isinstance(value, str):
        if (
            format_name in DATE_FORMATS
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and float(value).is_integer()
        ):
            value = str(int(value))
        else:
            raise ValueError(
                "Observation/availability timestamps must be ISO strings; convert Unix timestamps explicitly"
            )
    stamp = (
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        if format_name == "iso"
        else _date_parse(value, format_name)
    )
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
    if not config["observed_at_column"] and not config.get("timestamp_parts"):
        raise ValueError("Choose an observation timestamp column")
    if (
        config["availability_mode"] == "column"
        and not config["available_at_column"]
        and not config.get("available_at_parts")
    ):
        raise ValueError("Choose a publication/availability column")
    rows = read_records(content, format_name)
    if config.get("filter"):
        condition = config["filter"]
        rows = [row for row in rows if row.get(condition["column"]) == condition["equals"]]
        if not rows:
            raise ValueError("No observations match the exact entity filter")
    info["quality"]["selected_rows"] = len(rows)
    observations, keys = [], set()
    for row in rows:
        observed = _row_time(row, config)
        if config["availability_mode"] == "column":
            available = _row_time(row, config, available=True)
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
                        else text == needle
                        if item["operation"] == "equals"
                        else needle in text
                    )
                )
        if not values and config.get("aggregation", {}).get("operation") != "count":
            continue
        key = (observed, available, tuple(sorted(values)))
        if key in keys and not config.get("aggregation"):
            raise ValueError(
                "Duplicate observation/revision keys are ambiguous; aggregate or disambiguate first"
            )
        keys.add(key)
        observations.append(Observation(observed, available, values))
    if config.get("aggregation"):
        aggregation = config["aggregation"]
        groups: dict[datetime, list[Observation]] = {}
        for item in observations:
            start = item.observed_at.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
            if aggregation["frequency"] == "month":
                start = start.replace(day=1)
                end = datetime(
                    start.year + (start.month == 12),
                    1 if start.month == 12 else start.month + 1,
                    1,
                    tzinfo=UTC,
                )
            groups.setdefault(end, []).append(item)
        observations = []
        for end, group in groups.items():
            values = {"event_count": float(len(group))}
            if aggregation["operation"] != "count":
                values = {}
                for field in aggregation["fields"]:
                    raw = [item.values[field] for item in group if field in item.values]
                    value = (
                        None
                        if not raw or any(v is None for v in raw)
                        else sum(v for v in raw if v is not None)
                    )
                    if value is not None and aggregation["operation"] == "mean":
                        value /= len(raw)
                    if value is not None and not math.isfinite(value):
                        raise ValueError(
                            "Aggregate arithmetic exceeded finite numeric limits; rescale the source values"
                        )
                    values[f"{field}__{aggregation['operation']}_{aggregation['frequency']}"] = (
                        value
                    )
            observations.append(
                Observation(end, max(end, *(item.available_at for item in group)), values)
            )
    return sorted(observations, key=lambda r: r.available_at), info


def align_features(
    bars: list[Bar],
    observations: list[Observation],
    info: dict,
    bar_seconds: float = 86400,
    decision_delay_seconds: float = 0.0,
) -> list[dict[str, float | None]]:
    """Linear sweep of publications, retaining the latest known revision by observation time."""
    if not math.isfinite(decision_delay_seconds) or decision_delay_seconds < 0:
        raise ValueError("Decision delay must be nonnegative and finite")
    fields = info["generated_fields"]
    age = info["mapping"]["max_age_hours"] * 3600
    published: dict[str, tuple[datetime, datetime, float | None]] = {}
    cursor, result = 0, []
    for index, bar in enumerate(bars):
        when = bar.timestamp + timedelta(seconds=bar_seconds + decision_delay_seconds)
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
    parts = _parts(
        mapping, "timestamp_parts", list(dict.fromkeys(key for row in rows for key in row))
    )
    fields = {name: mapping.get(name, name) for name in ("open", "high", "low", "close", "volume")}
    required = [
        *(parts.values() if parts else [time_column]),
        *(fields[name] for name in ("open", "high", "low", "close")),
    ]
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
    if mapping.get("period_boundary", "start") not in {"start", "end"}:
        raise ValueError("Calendar period boundary must be start or end")
    bars = []
    try:
        for row in rows:
            if any(isinstance(row.get(fields[name]), bool) for name in fields):
                raise ValueError("OHLCV prices and volumes must be measurements, not boolean flags")
            bars.append(
                Bar(
                    _row_time(
                        row,
                        {
                            **mapping,
                            "observed_at_column": time_column,
                            "timestamp_parts": parts,
                            "period_boundary": mapping.get("period_boundary", "start"),
                        },
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
            "Imported market rows must be completed intervals and timestamps are bar OPEN times. Coarse calendar market bars use period start unless explicitly changed. Set the actual bar duration and quote-currency assumptions before running. Corporate-action and survivorship adjustments remain the source owner's responsibility."
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
