"""Bounded extraction/training requests to a service selected and operated by the user.

No framework, model weight, file upload, filesystem read or persistence is hidden
behind this adapter. A local manifest is path metadata for the selected loopback
service; that service owns preprocessing, hardware, training and its retention.
"""

from __future__ import annotations

import ast
import hashlib
import http.client
import ipaddress
import json
import math
import ntpath
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from typing import Any

from .algorithms import SignalInterpreter
from .data import timestamp
from .features import inspect_dataset, read_records
from .sources import _PinnedHTTPSHandler

SCHEMA = "hypothesis-lab/compute-v1"
MAX_REQUEST_BYTES = 6_000_000
MAX_RESPONSE_BYTES = 4_000_000
MAX_ROWS = 5000
SECRET_NAMES = {
    "apikey",
    "token",
    "accesstoken",
    "secret",
    "password",
    "authorization",
    "credential",
}


class ComputeError(ValueError):
    """A bounded, sanitized compute protocol or transport error."""


def _text(value: Any, label: str, maximum: int = 2000, *, empty: bool = False) -> str:
    if (
        not isinstance(value, str)
        or len(value) > maximum
        or (not empty and not value.strip())
        or "\x00" in value
    ):
        raise ComputeError(f"{label} must be bounded text")
    return value


def _integer(value: Any, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ComputeError(f"{label} must be an integer from {minimum} to {maximum}")
    return value


def _stamp(value: Any, label: str) -> str:
    try:
        return timestamp(_text(value, label, 80)).isoformat()
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise ComputeError(f"{label} must be a timezone-aware ISO timestamp") from None


def _names(value: Any) -> list[str]:
    if (
        not isinstance(value, list)
        or not 1 <= len(value) <= 32
        or any(not isinstance(v, str) or not v or len(v) > 128 for v in value)
        or len(set(value)) != len(value)
    ):
        raise ComputeError("Feature names must be 1..32 distinct bounded strings")
    return value


def _json_value(value: Any, depth: int = 0) -> None:
    if depth > 8:
        raise ComputeError("Service settings exceed eight nested levels")
    if isinstance(value, dict):
        if len(value) > 100:
            raise ComputeError("Service settings have too many fields")
        for key, item in value.items():
            _text(key, "Setting name", 128)
            if re.sub(r"[^a-z]", "", key.casefold()) in SECRET_NAMES:
                raise ComputeError(
                    "Keep credentials out of task/options; use the separate session key"
                )
            _json_value(item, depth + 1)
    elif isinstance(value, list):
        if len(value) > 1000:
            raise ComputeError("Service settings contain an oversized list")
        for item in value:
            _json_value(item, depth + 1)
    elif isinstance(value, str):
        _text(value, "Setting value", 16000, empty=True)
    elif value is not None and not isinstance(value, bool):
        try:
            finite = isinstance(value, (int, float)) and math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            raise ComputeError("Service settings must contain finite JSON values")


def _endpoint(connection: dict) -> tuple[str, bool]:
    if not isinstance(connection, dict) or set(connection) - {
        "endpoint",
        "allow_remote",
        "timeout_seconds",
    }:
        raise ComputeError("Compute connection supports endpoint, allow_remote and timeout_seconds")
    url = _text(connection.get("endpoint"), "Compute endpoint", 2000)
    if any(ord(c) < 32 or ord(c) == 127 for c in url):
        raise ComputeError("Compute endpoint contains control characters")
    try:
        parsed = urllib.parse.urlsplit(url)
        port = parsed.port
    except ValueError:
        raise ComputeError("Choose a valid compute endpoint URL") from None
    if (
        parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.hostname
    ):
        raise ComputeError("Keep credentials and queries out of compute URLs")
    local = parsed.hostname.casefold() in {"localhost", "127.0.0.1", "::1"}
    if local:
        if parsed.scheme not in {"http", "https"}:
            raise ComputeError("Loopback compute services must use HTTP or HTTPS")
    else:
        if (
            parsed.scheme != "https"
            or connection.get("allow_remote") is not True
            or port not in {None, 443}
        ):
            raise ComputeError(
                "Remote compute requires explicit allow_remote and public HTTPS on port 443"
            )
        if parsed.hostname.casefold().endswith((".local", ".internal", ".localhost")):
            raise ComputeError("Remote compute must use a public internet address")
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ComputeError("Remote compute cannot address private or metadata-service IPs")
    if "allow_remote" in connection and not isinstance(connection["allow_remote"], bool):
        raise ComputeError("Choose allow_remote explicitly as true or false")
    _integer(connection.get("timeout_seconds", 60), "Compute timeout seconds", 1, 120)
    return url, local


def _loopback_socket(host: str, port: int, timeout: Any):
    answers = list(
        dict.fromkeys(
            str(item[4][0]) for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        )
    )
    if not answers or any(not ipaddress.ip_address(address).is_loopback for address in answers):
        raise ComputeError("Local compute must resolve only to loopback addresses")
    last: OSError | None = None
    for address in answers:
        try:
            return socket.create_connection((address, port), timeout=timeout)
        except OSError as error:
            last = error
    raise last or OSError("Loopback connection unavailable")


class _LoopbackHTTP(http.client.HTTPConnection):
    def connect(self) -> None:
        self.sock = _loopback_socket(self.host, self.port, self.timeout)


class _LoopbackHTTPS(http.client.HTTPSConnection):
    _context: ssl.SSLContext

    def connect(self) -> None:
        connection = _loopback_socket(self.host, self.port, self.timeout)
        try:
            self.sock = self._context.wrap_socket(connection, server_hostname=self.host)
        except Exception:
            connection.close()
            raise


class _LoopbackHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, request):
        return self.do_open(_LoopbackHTTP, request)


class _LoopbackHTTPSHandler(urllib.request.HTTPSHandler):
    _context: ssl.SSLContext

    def https_open(self, request):
        return self.do_open(_LoopbackHTTPS, request, context=self._context)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        response.close()
        raise ComputeError(
            "Compute service redirected the request; credentials and local paths were not forwarded"
        )


def _request(connection: dict, payload: dict, credential: str | None) -> dict:
    url, local = _endpoint(connection)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if credential is not None:
        if (
            not isinstance(credential, str)
            or not 1 <= len(credential) <= 2048
            or any(not 32 <= ord(c) <= 126 for c in credential)
        ):
            raise ComputeError("Use a printable session-only compute credential")
        headers["Authorization"] = "Bearer " + credential
        if (len(credential) >= 8 and credential in url) or credential in urllib.parse.urlsplit(
            url
        ).path.split("/"):
            raise ComputeError(
                "Keep session credentials out of endpoint paths as well as query strings"
            )
    body = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode()
    if len(body) > MAX_REQUEST_BYTES:
        raise ComputeError("Compute request exceeds 6 MB; use a local manifest or a smaller table")
    if (
        credential
        and len(credential) >= 8
        and (credential.encode() in body or json.dumps(credential)[1:-1].encode() in body)
    ):
        raise ComputeError(
            "A session credential appeared in the request body; keep it in the separate key field"
        )
    handlers = (
        [_LoopbackHTTPHandler(), _LoopbackHTTPSHandler()] if local else [_PinnedHTTPSHandler()]
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect(), *handlers)

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ComputeError("Compute response JSON keys must be distinct")
            value[key] = item
        return value

    def invalid(value):
        raise ComputeError("Compute response contains nonfinite JSON")

    try:
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        deadline = time.monotonic() + connection.get("timeout_seconds", 60)
        with opener.open(request, timeout=connection.get("timeout_seconds", 60)) as response:
            chunks, size = [], 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ComputeError(
                        "Compute response exceeded the requested wait budget; check service status before retrying"
                    )
                network_socket = getattr(
                    getattr(getattr(response, "fp", None), "raw", None), "_sock", None
                )
                if network_socket is not None:
                    network_socket.settimeout(remaining)
                chunk = getattr(response, "read1", response.read)(
                    min(65536, MAX_RESPONSE_BYTES - size + 1)
                )
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_RESPONSE_BYTES:
                    raise ComputeError(
                        "Compute response exceeds 4 MB; request a smaller structured result"
                    )
                chunks.append(chunk)
        raw = b"".join(chunks)
        result = json.loads(
            raw.decode("utf-8-sig"), parse_constant=invalid, object_pairs_hook=unique
        )
        if not isinstance(result, dict):
            raise ComputeError("Compute service must return a JSON object")
        return result
    except ComputeError:
        raise
    except urllib.error.HTTPError as error:
        error.close()
        raise ComputeError(
            f"Compute service returned HTTP {error.code}; inspect the selected service and its access/budget"
        ) from None
    except (urllib.error.URLError, OSError, TimeoutError, UnicodeError, ValueError, RecursionError):
        raise ComputeError(
            "Compute service was unavailable, timed out or returned invalid JSON; no credential/body was logged"
        ) from None


def _task(value: Any, operation: str) -> dict:
    allowed = {
        "description",
        "feature_names",
        "target_field",
        "target_type",
        "horizon",
        "target_condition",
        "training_start",
        "training_end",
        "evaluation_start",
        "evaluation_end",
    }
    if not isinstance(value, dict) or set(value) - allowed:
        raise ComputeError("Choose a structured compute task using the documented fields")
    task = dict(value)
    if "description" in task:
        _text(task["description"], "Task description", 2000)
    if "feature_names" in task:
        task["feature_names"] = _names(task["feature_names"])
    if operation in {"train", "evaluate"} or "target_type" in task:
        if not isinstance(task.get("target_type"), str) or task.get("target_type") not in {
            "increase",
            "return",
            "level",
            "condition",
        }:
            raise ComputeError("Choose increase, return, level or condition as the target type")
        task["horizon"] = _integer(task.get("horizon", 1), "Target horizon", 1, 30)
        if task["target_type"] == "condition":
            expression = _text(task.get("target_condition"), "Future target condition", 2000)
            # Interpret a harmless numeric schema probe; never execute generated Python.
            try:
                tree = ast.parse(expression, mode="eval")
                names = set(task.get("feature_names", []))
                names.update(node.id for node in ast.walk(tree) if isinstance(node, ast.Name))
                names.update(
                    node.args[0].value
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "col"
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                )
                names.update(
                    "market." + name
                    for name in ("open", "high", "low", "close", "volume", "return_1")
                )
                dummy: list[dict[str, float | bool | None]] = [
                    {name: 1.0 for name in names} for _ in range(2)
                ]
                probe = SignalInterpreter(dummy).run(expression)
                if any(value is not None and not isinstance(value, bool) for value in probe):
                    raise ValueError("Future conditions must produce Boolean outcomes")
            except (ValueError, TypeError, KeyError, OverflowError, SyntaxError, RecursionError):
                raise ComputeError(
                    "Target condition must use the documented bounded signal expression grammar"
                ) from None
        else:
            _text(task.get("target_field"), "Target field", 128)
            if "target_condition" in task:
                raise ComputeError("target_condition is only used with target_type condition")
    for name in ("training_start", "training_end", "evaluation_start", "evaluation_end"):
        if name in task:
            task[name] = _stamp(task[name], name)
    if operation == "train" and "training_end" not in task:
        raise ComputeError("Training requires a declared training_end timestamp")
    if operation == "evaluate" and not {"evaluation_start", "evaluation_end"} <= task.keys():
        raise ComputeError("Evaluation requires explicit evaluation_start and evaluation_end")
    for first, last in (
        ("training_start", "training_end"),
        ("evaluation_start", "evaluation_end"),
        ("training_end", "evaluation_start"),
    ):
        if first in task and last in task and timestamp(task[first]) >= timestamp(task[last]):
            raise ComputeError(
                "Training and evaluation boundaries must be chronological and disjoint"
            )
    _json_value(task)
    return task


def _has_local_path(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_has_local_path(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_local_path(item) for item in value)
    return isinstance(value, str) and (
        value.casefold().startswith("file://")
        or value.startswith(("/", "\\"))
        or bool(re.match(r"^[A-Za-z]:[\\/]", value))
    )


def _input(value: Any, local: bool) -> tuple[dict, list[str], dict]:
    if not isinstance(value, dict):
        raise ComputeError("Choose an inline table or an explicit local-file manifest")
    if value.get("kind") == "manifest":
        if not local:
            raise ComputeError(
                "Local path manifests can only be sent to a loopback service; remote compute needs an explicitly supplied inline table"
            )
        if set(value) - {"kind", "files"}:
            raise ComputeError("Manifest input supports kind and files only")
        files = value.get("files")
        if not isinstance(files, list) or not 1 <= len(files) <= 128:
            raise ComputeError("Choose one to 128 local manifest files")
        paths = []
        for item in files:
            if not isinstance(item, dict) or set(item) - {
                "path",
                "role",
                "media_type",
                "description",
                "sha256",
            }:
                raise ComputeError(
                    "Manifest files support path, role, media_type, description and optional declared sha256"
                )
            path = _text(item.get("path"), "Local manifest path", 2048)
            if (
                any(ord(c) < 32 for c in path)
                or path.startswith(("\\\\", "//"))
                or not (
                    path.startswith("/") or ntpath.isabs(path) and bool(ntpath.splitdrive(path)[0])
                )
            ):
                raise ComputeError(
                    "Manifest paths must be absolute local paths, not URLs, network shares or relative paths"
                )
            if item.get("role") not in {"source", "train", "validation", "test"}:
                raise ComputeError("Each manifest file needs a source/train/validation/test role")
            for key in ("media_type", "description"):
                if key in item:
                    _text(item[key], "Manifest description", 500)
            if "sha256" in item and (
                not isinstance(item["sha256"], str)
                or not re.fullmatch(r"[a-fA-F0-9]{64}", item["sha256"])
            ):
                raise ComputeError("A declared manifest SHA-256 must contain 64 hex characters")
            paths.append(path)
        if len(set(paths)) != len(paths):
            raise ComputeError("Manifest paths must be distinct")
        return value, paths, {"kind": "manifest", "files": len(files), "contents_uploaded": False}
    if value.get("kind") == "table":
        if set(value) - {"kind", "content", "format", "mapping"}:
            raise ComputeError("Table input supports kind, content, format and mapping only")
        format_name = value.get("format", "csv")
        try:
            rows = read_records(value.get("content", ""), format_name)
        except (ValueError, TypeError, OverflowError, RecursionError):
            raise ComputeError(
                "Inline compute data must be a supported bounded table, not an opaque binary upload"
            ) from None
        if len(rows) > MAX_ROWS:
            raise ComputeError("Inline compute tables are capped at 5,000 rows")
        if not local and _has_local_path(rows):
            raise ComputeError(
                "Remote inline tables contain local path values; remove those fields explicitly before sending"
            )
        if "mapping" in value and not isinstance(value["mapping"], dict):
            raise ComputeError("Inline table mapping must be an object")
        if "mapping" in value:
            _json_value(value["mapping"])
        return (
            value,
            [],
            {"kind": "table", "rows": len(rows), "format": format_name, "contents_uploaded": True},
        )
    raise ComputeError("Compute input kind must be table or manifest")


def _clean(value: Any, credential: str | None, paths: list[str]) -> Any:
    if isinstance(value, dict):
        return {
            key: _clean(item, credential, paths)
            for key, item in value.items()
            if re.sub(r"[^a-z]", "", key.casefold()) not in SECRET_NAMES
            and not key.casefold().endswith(("path", "paths", "directory"))
        }
    if isinstance(value, list):
        return [_clean(item, credential, paths) for item in value]
    if isinstance(value, str):
        if credential and value == credential:
            value = "[redacted]"
        elif credential and len(credential) >= 8:
            value = value.replace(credential, "[redacted]")
        for path in paths:
            if ntpath.splitdrive(path)[0]:
                pattern = re.escape(path).replace(r"\\", r"[\\/]")
                value = re.sub(pattern, "[redacted]", value, flags=re.IGNORECASE)
            else:
                value = value.replace(path, "[redacted]")
        return value
    return value


def _dataset(value: Any, acquired: str) -> dict:
    if not isinstance(value, dict) or set(value) - {"records", "mapping", "provenance"}:
        raise ComputeError("Extracted dataset supports records, mapping and provenance only")
    records = value.get("records")
    if not isinstance(records, list) or not 1 <= len(records) <= MAX_ROWS:
        raise ComputeError("Extracted dataset needs one to 5,000 canonical records")
    try:
        records = read_records(json.dumps(records, allow_nan=False), "json")
    except (ValueError, TypeError, OverflowError, RecursionError):
        raise ComputeError("Extracted records must be bounded finite tabular JSON") from None
    assumed = False
    for row in records:
        row["observed_at"] = _stamp(row.get("observed_at"), "Extracted observation time")
        if "available_at" not in row:
            row["available_at"] = acquired
            assumed = True
        else:
            row["available_at"] = _stamp(row["available_at"], "Extracted publication time")
        if timestamp(row["available_at"]) < timestamp(row["observed_at"]):
            raise ComputeError("Extracted information cannot be published before its observation")
    mapping = value.get("mapping", {})
    if not isinstance(mapping, dict) or mapping.get("availability_mode", "column") != "column":
        raise ComputeError(
            "Canonical extracted records use their actual available_at column; do not override it with a lag"
        )
    mapping = {
        **mapping,
        "observed_at_column": "observed_at",
        "timestamp_column": "observed_at",
        "available_at_column": "available_at",
        "timestamp_format": "iso",
        "available_at_format": "iso",
        "availability_mode": "column",
        "timestamp_parts": {},
        "available_at_parts": {},
    }
    content = json.dumps(records, allow_nan=False, separators=(",", ":"))
    provenance = value.get("provenance", {})
    if not isinstance(provenance, dict):
        raise ComputeError("Extracted provenance must be a bounded JSON object")
    _json_value(provenance)
    try:
        info = inspect_dataset(content, "json", mapping)
    except (ValueError, TypeError, OverflowError):
        raise ComputeError(
            "Extracted dataset mapping does not match the returned measured fields"
        ) from None
    return {
        "content": content,
        "format": "json",
        "records": records,
        "mapping": info["mapping"],
        "inspection": info,
        "provenance": provenance,
        "warnings": [
            "Missing publication timestamps defaulted to acquisition time; no historical availability was inferred."
        ]
        if assumed
        else [],
    }


def _prediction(value: Any, connection: dict, task: dict) -> tuple[dict, dict, dict]:
    if not isinstance(value, dict) or set(value) - {
        "connection",
        "feature_names",
        "trained_through",
    }:
        raise ComputeError(
            "Training must return a reusable prediction connection, feature_names and trained_through; opaque executable artifacts are unsupported"
        )
    names = _names(value.get("feature_names"))
    if task.get("feature_names") and task["feature_names"] != names:
        raise ComputeError("Returned model feature order differs from the requested training task")
    trained = _stamp(value.get("trained_through"), "Model trained_through")
    if (
        timestamp(trained) > timestamp(task["training_end"])
        or task.get("evaluation_start")
        and timestamp(trained) >= timestamp(task["evaluation_start"])
    ):
        raise ComputeError(
            "Declared trained_through overlaps evaluation or exceeds the requested training boundary"
        )
    if task.get("training_start") and timestamp(trained) < timestamp(task["training_start"]):
        raise ComputeError("Declared trained_through precedes the requested training window")
    proposed = value.get("connection")
    if (
        not isinstance(proposed, dict)
        or set(proposed) - {"kind", "endpoint", "output_field", "output_kind", "max_calls"}
        or proposed.get("kind") != "tabular"
    ):
        raise ComputeError(
            "Prediction reuse supports the documented numeric tabular endpoint contract"
        )
    address, _ = _endpoint(
        {
            "endpoint": proposed.get("endpoint"),
            "allow_remote": connection.get("allow_remote", False),
        }
    )

    def origin(url):
        parsed = urllib.parse.urlsplit(url)
        return (
            parsed.scheme,
            parsed.hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
        )

    if origin(address) != origin(connection["endpoint"]):
        raise ComputeError(
            "Returned prediction endpoint must share the selected compute service origin; review a different service separately"
        )
    output_field = proposed.get("output_field", "predictions")
    if not isinstance(output_field, str) or not re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){0,7}", output_field
    ):
        raise ComputeError("Choose a bounded dotted numeric prediction response field")
    kind = "probability" if task["target_type"] in {"increase", "condition"} else "prediction"
    if proposed.get("output_kind", kind) != kind:
        raise ComputeError(
            "Returned output kind does not match the declared classification/regression task"
        )
    public = {
        "kind": "tabular",
        "endpoint": address,
        "output_field": output_field,
        "output_kind": kind,
        "max_calls": _integer(proposed.get("max_calls", 12), "Prediction call budget", 1, 64),
        "allow_remote": connection.get("allow_remote", False),
    }
    config = {
        key: task[key]
        for key in ("target_field", "target_type", "target_condition", "horizon")
        if key in task
    }
    config.update(feature_names=names)
    return (
        public,
        config,
        {"trained_through": trained, "status": "service declaration; not independently verified"},
    )


def _evaluation(value: Any, task: dict) -> dict:
    if not isinstance(value, dict) or set(value) != {"metrics", "rows", "start", "end"}:
        raise ComputeError("Evaluation returns metrics, rows, start and end only")
    metrics = value["metrics"]
    if not isinstance(metrics, dict) or not 1 <= len(metrics) <= 32:
        raise ComputeError("Evaluation needs one to 32 named numeric metrics")
    for name, number in metrics.items():
        _text(name, "Metric name", 80)
        try:
            finite = (
                number is None
                or not isinstance(number, bool)
                and isinstance(number, (int, float))
                and math.isfinite(number)
            )
        except OverflowError:
            finite = False
        if not finite:
            raise ComputeError(
                "Evaluation metrics must be finite numbers or null, not executable or text values"
            )
    start, end = _stamp(value["start"], "Evaluation start"), _stamp(value["end"], "Evaluation end")
    if timestamp(start) >= timestamp(end):
        raise ComputeError("Evaluation start must precede end")
    if (
        task.get("evaluation_start")
        and timestamp(start) < timestamp(task["evaluation_start"])
        or task.get("evaluation_end")
        and timestamp(end) > timestamp(task["evaluation_end"])
    ):
        raise ComputeError("Returned evaluation lies outside the declared evaluation window")
    return {
        "metrics": metrics,
        "rows": _integer(value["rows"], "Evaluated rows", 1, 10_000_000),
        "start": start,
        "end": end,
        "status": "service-reported metrics; not independently recomputed",
    }


def run_compute(connection: dict, request: dict, credential: str | None = None) -> dict:
    """Execute one bounded synchronous user-service job, returning reviewable data/settings."""
    _, local = _endpoint(connection)
    if (
        not isinstance(request, dict)
        or set(request) - {"schema", "operation", "input", "task", "options"}
        or request.get("schema", SCHEMA) != SCHEMA
    ):
        raise ComputeError("Use the documented compute-v1 request object")
    operation = request.get("operation")
    if not isinstance(operation, str) or operation not in {"extract", "train", "evaluate"}:
        raise ComputeError("Choose extract, train or evaluate")
    task = _task(request.get("task", {}), operation)
    options = request.get("options", {})
    if not isinstance(options, dict):
        raise ComputeError("Service options must be a finite JSON object")
    _json_value(options)
    if not local and (_has_local_path(options) or _has_local_path(task)):
        raise ComputeError(
            "Remote compute cannot receive local path settings; select a remote model by its service-side identifier"
        )
    source, paths, summary = _input(request.get("input"), local)
    payload = {
        "schema": SCHEMA,
        "operation": operation,
        "input": source,
        "task": task,
        "options": options,
    }
    started = time.monotonic()
    response = _request(connection, payload, credential)
    allowed = {
        "schema",
        "status",
        "operation",
        "task",
        "dataset",
        "prediction",
        "evaluation",
        "provenance",
        "warnings",
    }
    if (
        set(response) - allowed
        or response.get("schema") != SCHEMA
        or response.get("status") != "complete"
        or response.get("operation") != operation
    ):
        raise ComputeError(
            "Service must return a completed compute-v1 structured response; long jobs, code and opaque model artifacts are not accepted"
        )
    if response.get("task") != task:
        raise ComputeError(
            "Service response must echo the exact declared task/target/conditions; refusing an ambiguous training result"
        )
    response = _clean(response, credential, paths)
    acquired = datetime.now(UTC).isoformat()
    warnings = response.get("warnings", [])
    if (
        not isinstance(warnings, list)
        or len(warnings) > 20
        or any(not isinstance(item, str) or len(item) > 1000 for item in warnings)
    ):
        raise ComputeError("Service warnings must be a bounded list of text")
    provenance = response.get("provenance", {})
    if not isinstance(provenance, dict):
        raise ComputeError("Service provenance must be a bounded JSON object")
    _json_value(provenance)
    result = {
        "schema": SCHEMA,
        "status": "complete",
        "operation": operation,
        "task": _clean(task, credential, paths),
        "input_summary": summary,
        "latency_seconds": time.monotonic() - started,
        "provenance": {
            "service": connection["endpoint"],
            "acquired_at": acquired,
            "storage": "session only; selected user service has its own retention policy",
            "request_sha256": hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode()
            ).hexdigest(),
            "service_declaration": provenance,
        },
        "warnings": list(warnings)
        + [
            "The selected service controls preprocessing, hardware, models, training and retention. Its metrics and provenance are declarations, not independent audit evidence."
        ],
    }
    if operation == "extract" and "dataset" not in response:
        raise ComputeError("Extraction must return a canonical records dataset")
    if "dataset" in response:
        result["dataset"] = _dataset(response["dataset"], acquired)
    if operation == "train":
        prediction, model_config, training = _prediction(
            response.get("prediction"), connection, task
        )
        result.update(
            prediction_connection=prediction,
            model_config=model_config,
            training_provenance=training,
        )
    elif "prediction" in response:
        raise ComputeError("Prediction service creation belongs to the explicit train operation")
    if operation == "evaluate" and "evaluation" not in response:
        raise ComputeError("Evaluation must return named structured numeric metrics")
    if "evaluation" in response:
        result["evaluation"] = _evaluation(response["evaluation"], task)
    return result
