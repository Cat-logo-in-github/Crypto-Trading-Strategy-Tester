"""Optional user-controlled model/LLM endpoints. No weights or SDK are bundled."""

from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict
from datetime import timedelta
from typing import Any

from .data import Bar, validate_bars
from .engine import Decision, ExecutionConfig, backtest, benchmark
from .models import _decision_config, _diagnostics, _integer, _names, _number, prediction_decision

PUBLIC_CONNECTION_FIELDS = {
    "kind",
    "endpoint",
    "model",
    "allow_remote",
    "prompt",
    "signal",
    "output_field",
    "phrase",
    "output_kind",
    "max_calls",
    "max_tokens",
    "temperature",
}


def _redact(text: str, credential: str | None) -> str:
    if credential:
        text = text.replace(credential, "[redacted]")
        escaped = json.dumps(credential)[1:-1]
        if escaped != credential:
            text = text.replace(escaped, "[redacted]")
    return text


def public_connection(connection: dict, credential: str | None = None) -> dict:
    """Keep only supported public endpoint settings; never export auth fields."""
    return {
        key: _redact(value, credential) if isinstance(value, str) else value
        for key, value in connection.items()
        if key in PUBLIC_CONNECTION_FIELDS
        and (
            value is None
            or isinstance(value, (str, bool, int))
            or isinstance(value, float)
            and math.isfinite(value)
        )
    }


def _token_count(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(
            "Reported token counts must be nonnegative integers; no counts were estimated"
        )
    return value


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError(
            "Model endpoint redirected the request; enter the final endpoint. Credentials were not forwarded."
        )


def endpoint_url(config: dict) -> str:
    url = config.get("endpoint", "")
    if not isinstance(url, str) or not url or len(url) > 2000 or any(ord(c) < 32 for c in url):
        raise ValueError("Choose a local model endpoint or an explicitly authorized HTTPS endpoint")
    parsed = urllib.parse.urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Keep credentials out of model URLs; use the session key field")
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme not in {"http", "https"} or (
        not local and (parsed.scheme != "https" or config.get("allow_remote") is not True)
    ):
        raise ValueError(
            "HTTP is allowed only for localhost. A remote HTTPS model requires an explicit allow_remote choice."
        )
    if not parsed.hostname:
        raise ValueError("Choose a valid model endpoint hostname")
    return url.rstrip("/")


def _request(config: dict, payload: dict, credential: str | None = None) -> dict:
    url = endpoint_url(config)
    if config.get("kind", "llm") == "llm" and not url.endswith("/chat/completions"):
        url += "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if credential:
        if (
            not isinstance(credential, str)
            or len(credential) > 2048
            or any(ord(c) < 32 or ord(c) > 126 for c in credential)
        ):
            raise ValueError("Use a printable session-only model credential")
        headers["Authorization"] = "Bearer " + credential
    request = urllib.request.Request(
        url, data=json.dumps(payload, allow_nan=False).encode(), headers=headers, method="POST"
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=60) as response:
            body = response.read(1_000_001)
        if len(body) > 1_000_000:
            raise ValueError("Model response exceeds 1 MB; reduce its output budget")
        result = json.loads(body)
        if not isinstance(result, dict):
            raise ValueError("The endpoint must return a JSON object")
        return result
    except urllib.error.HTTPError as error:
        raise ValueError(
            f"Model endpoint returned HTTP {error.code}. Check the model name, credentials, availability and budget."
        ) from None
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        raise ValueError(
            "The selected model endpoint is unavailable or returned invalid JSON. No credential or response body was logged."
        ) from None


def _path(value: Any, path: str) -> Any:
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise ValueError("The configured numeric output field was absent from the response")
        value = value[part]
    return value


def call_llm(config: dict, prompt: str, credential: str | None = None) -> dict:
    model = config.get("model", "")
    budget = _integer(config.get("max_tokens", 128), "Output token budget", 1, 2048)
    if (
        not isinstance(model, str)
        or not 1 <= len(model) <= 200
        or not isinstance(prompt, str)
        or len(prompt) > 16000
    ):
        raise ValueError(
            "Choose a model, 1..2,048 output tokens and a prompt under 16,000 characters"
        )
    started = time.monotonic()
    temperature = _number(config.get("temperature", 0), "Sampling temperature")
    if not 0 <= temperature <= 2:
        raise ValueError("Sampling temperature must be in [0,2]")
    response = _request(
        config,
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": budget,
            "stream": False,
        },
        credential,
    )
    try:
        text = response["choices"][0]["message"]["content"]
        if not isinstance(text, str):
            raise ValueError()
    except (KeyError, IndexError, TypeError, ValueError):
        raise ValueError(
            "Expected a text chat-completion response from the selected model"
        ) from None
    usage = response.get("usage", {})
    usage = usage if isinstance(usage, dict) else {}
    return {
        "text": _redact(text, credential)[:10000],
        "text_length": len(text),
        "completion_tokens": _token_count(usage.get("completion_tokens")),
        "prompt_tokens": _token_count(usage.get("prompt_tokens")),
        "total_tokens": _token_count(usage.get("total_tokens")),
        "latency_seconds": time.monotonic() - started,
        "reported_model": _redact(str(response.get("model", model)), credential)[:200],
    }


def extract_signal(response: dict, config: dict) -> float:
    method = config.get("signal", "json_field")
    value: Any
    if method in {"completion_tokens", "prompt_tokens", "total_tokens"}:
        value = _token_count(response.get(method))
        if value is None:
            raise ValueError(
                "The endpoint did not report that token count. Counts are never estimated silently."
            )
    elif method == "text_length":
        value = response.get("text_length", len(response["text"]))
    elif method == "text_contains":
        phrase = config.get("phrase", "")
        if not isinstance(phrase, str) or not phrase:
            raise ValueError("Choose a phrase to match in the LLM output")
        value = float(phrase.casefold() in response["text"].casefold())
    elif method == "json_field":
        try:
            value = _path(
                json.loads(response["text"]), str(config.get("output_field", "probability"))
            )
        except (json.JSONDecodeError, TypeError):
            raise ValueError(
                "Ask the model for strict JSON and choose its numeric output field"
            ) from None
    else:
        raise ValueError(
            "Choose json_field, completion_tokens, prompt_tokens, total_tokens, text_contains or text_length"
        )
    if isinstance(value, bool):
        value = float(value)
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("The selected model signal was not numeric") from None
    if not math.isfinite(number):
        raise ValueError("The selected model signal must be finite")
    return number


def llm_plan(query: str, config: dict, credential: str | None = None) -> dict:
    prompt = (
        'Translate this research idea into a data-discovery plan. Return strict JSON only: {"search_terms":"short catalog search phrase","required_measurements":["..."],"candidate_signal":"explicit measurable definition","clarifications":["..."]}. Do not invent datasets, URLs, historical availability or predictive relationships. Idea: '
        + query[:2000]
    )
    response = call_llm(config, prompt, credential)
    try:
        value = json.loads(response["text"])
    except json.JSONDecodeError:
        raise ValueError(
            "The selected LLM did not return a strict JSON data plan; use the guided planner or adjust the model"
        ) from None
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("search_terms"), str)
        or not 2 <= len(value["search_terms"]) <= 200
    ):
        raise ValueError("The model plan must contain a short search_terms string")
    for key in ("required_measurements", "clarifications"):
        entries = value.get(key, [])
        if not isinstance(entries, list) or any(not isinstance(entry, str) for entry in entries):
            raise ValueError("Model plan measurements and clarifications must be lists of strings")
    if not isinstance(value.get("candidate_signal", ""), str):
        raise ValueError("The candidate signal must be a short text definition")
    return {
        "search_terms": value["search_terms"],
        "required_measurements": [
            entry[:500] for entry in value.get("required_measurements", [])[:10]
        ],
        "candidate_signal": value.get("candidate_signal", "")[:1500],
        "clarifications": [entry[:500] for entry in value.get("clarifications", [])[:10]],
        "warning": "LLM-generated candidate plan. Validate concepts, mappings and source metadata; the output is not executed as code or accepted as evidence.",
        "usage": {k: response[k] for k in ("completion_tokens", "prompt_tokens", "total_tokens")},
    }


def run_endpoint_model(
    bars: list[Bar],
    feature_rows: list[dict],
    config: dict,
    connection: dict,
    credential: str | None = None,
) -> dict:
    """Bounded historical inference replay through a user-selected local/HTTPS service."""
    endpoint_url(connection)
    validate_bars(bars)
    if len(feature_rows) != len(bars) or any(not isinstance(row, dict) for row in feature_rows):
        raise ValueError("Provide one named-column feature row per market bar")
    names = _names(config.get("feature_names", []))
    count = _integer(connection.get("max_calls", 12), "Inference call budget", 1, 64)
    start = _integer(
        config.get("evaluation_start_index", max(int(len(bars) * 0.8), len(bars) - count - 1)),
        "Evaluation start",
        0,
        len(bars) - 2,
    )
    if not 0 <= start < len(bars) - 1:
        raise ValueError("Choose an evaluation start before the final market bar")
    indices = [
        i
        for i in range(start, len(bars) - 1)
        if all(feature_rows[i].get(name) is not None for name in names)
    ]
    if not indices or len(indices) > count:
        raise ValueError(
            "The selected evaluation needs more calls than its budget, or has no complete inputs. Choose a later start or increase the bounded budget."
        )
    execution = ExecutionConfig(
        **{
            name: float(config.get(name, value))
            for name, value in asdict(ExecutionConfig()).items()
        }
    )
    horizon = _integer(config.get("horizon", 1), "Forecast horizon", 1, 30)
    target_field = config.get("target_field", "market.close")
    target_type = config.get("target_type", "increase")
    if (
        not isinstance(target_field, str)
        or not target_field
        or target_type not in {"increase", "return", "level"}
    ):
        raise ValueError("Choose a named target field and increase, return or level target type")
    if target_field != "market.close" and not any(target_field in row for row in feature_rows):
        raise ValueError("The selected target field is absent from the aligned dataset")

    def actual_target(index: int) -> float | None:
        if index + horizon >= len(bars):
            return None
        first = (
            bars[index].close
            if target_field == "market.close"
            else feature_rows[index].get(target_field)
        )
        future = (
            bars[index + horizon].close
            if target_field == "market.close"
            else feature_rows[index + horizon].get(target_field)
        )
        if first is None or future is None:
            return None
        first, future = _number(first, "Target value"), _number(future, "Future target value")
        if target_type == "increase":
            return float(future > first)
        if target_type == "level":
            return future
        return _number(future / first - 1, "Target return") if first != 0 else None

    feature_values = {
        i: {name: _number(feature_rows[i][name], "Selected historical feature") for name in names}
        for i in indices
    }
    kind = connection.get(
        "output_kind",
        "probability" if connection.get("signal", "json_field") == "json_field" else "prediction",
    )
    if kind not in {"probability", "prediction"}:
        raise ValueError("Choose probability or prediction output kind")
    policy = _decision_config(config, kind)
    records: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]]
    if connection.get("kind", "llm") == "tabular":
        result = _request(
            connection,
            {
                "feature_names": names,
                "features": [[feature_values[i][name] for name in names] for i in indices],
                "model": connection.get("model"),
            },
            credential,
        )
        values = _path(result, connection.get("output_field", "predictions"))
        if not isinstance(values, list) or len(values) != len(indices):
            raise ValueError(
                "The tabular endpoint must return one configured scalar prediction per supplied row"
            )
        outputs = [
            {"value": _number(v, "Endpoint prediction"), "text": "", "completion_tokens": None}
            for v in values
        ]
    else:
        template = connection.get(
            "prompt",
            'Given these historical features, return strict JSON {"probability":0.5}: {features}',
        )
        if not isinstance(template, str) or "{features}" not in template:
            raise ValueError(
                "The prompt needs a literal {features} placeholder; future outcomes are not supplied"
            )
        outputs = []
        for i in indices:
            values = feature_values[i]
            response = call_llm(
                connection,
                template.replace("{features}", json.dumps(values, sort_keys=True))
                .replace("{target}", target_field)
                .replace("{horizon}", str(horizon)),
                credential,
            )
            response["value"] = extract_signal(response, connection)
            outputs.append(response)
    decisions: list[Decision | None] = [None] * (len(bars) - start)
    for i, response in zip(indices, outputs):
        decision, matched = prediction_decision(response["value"], policy)
        decisions[i - start] = decision
        actual = actual_target(i)
        forecast_correct = (
            ((response["value"] > 0.5) == bool(actual))
            if actual is not None and kind == "probability" and target_type == "increase"
            else None
        )
        records.append(
            {
                "timestamp": bars[i].timestamp.isoformat(),
                "decision_at": (
                    bars[i].timestamp + timedelta(seconds=execution.bar_seconds)
                ).isoformat(),
                "index": i,
                "bar_index": i,
                "features": feature_values[i],
                "prediction": response["value"],
                "probability": response["value"] if kind == "probability" else None,
                "actual": actual,
                "target_label_timestamp": bars[i + horizon].timestamp.isoformat()
                if i + horizon < len(bars)
                else None,
                "target_label_available_at": (
                    bars[i + horizon].timestamp + timedelta(seconds=execution.bar_seconds)
                ).isoformat()
                if i + horizon < len(bars)
                else None,
                "forecast_correct": forecast_correct,
                "condition_matched": matched,
                "decision": "long"
                if matched
                else "cash"
                if policy["when_false"] == "exit"
                else "hold",
                "intent": asdict(decision) if decision else None,
                "following_market_return": bars[i + 1].close / bars[i + 1].open - 1,
                "following_close_return": bars[i + 1].close / bars[i].close - 1,
                "output_text": _redact(response.get("text", ""), credential),
                "usage": {
                    key: response.get(key)
                    for key in ("completion_tokens", "prompt_tokens", "total_tokens")
                },
                "inference_latency_seconds": response.get("latency_seconds"),
                "forecast_market_discrepancy": bool(
                    forecast_correct is True and matched and bars[i + 1].close < bars[i + 1].open
                ),
            }
        )
    result = backtest(bars[start:], decisions, execution)
    orders = {order["submitted_bar"]: order for order in result["orders"]}
    for record in records:
        record["fills"] = [
            fill for fill in result["fills"] if fill["decision_bar_open"] == record["timestamp"]
        ]
        record["execution_status"] = orders.get(record["index"] - start, {}).get("status", "hold")
    labeled = [record for record in records if record["actual"] is not None]
    diagnostic_kind = (
        "probability" if kind == "probability" and target_type == "increase" else "prediction"
    )
    diagnostics = _diagnostics(
        [record["actual"] for record in labeled],
        [record["prediction"] for record in labeled],
        diagnostic_kind,
    )
    if target_type == "increase" and diagnostic_kind != "probability":
        diagnostics.pop("directional_accuracy", None)
    public_config_fields = {
        "feature_names",
        "target_field",
        "target_type",
        "horizon",
        "decision",
        "evaluation_start_index",
        *asdict(ExecutionConfig()),
    }
    public_config = {key: value for key, value in config.items() if key in public_config_fields}
    return {
        "mode": "endpoint-replay",
        "model": {"family": "user_endpoint", "output_kind": kind, "feature_names": names},
        "configuration": {
            **public_config,
            "connection": public_connection(connection, credential),
            "decision": policy,
            "target_field": target_field,
            "target_type": target_type,
            "horizon": horizon,
        },
        "target": f"{target_field}[t+{horizon}] compared with current {target_type}",
        "test": diagnostics,
        "validation": {"rows": 0, "mse": None, "mae": None, "directional_accuracy": None},
        "predictions": records,
        "inference_decisions": records,
        "backtest": result,
        "benchmark": benchmark(bars[start:], execution),
        "warnings": [
            "Historical model/LLM replay: pretraining knowledge and data provenance are unknown. This is not a verified out-of-sample model evaluation.",
            "Prompts contain configured historical features only. Modern LLMs can still contain future knowledge; token behavior can vary across model versions, servers, seeds and sampling settings.",
            "Inference occurs now. Historical trade times are simulation times, not historical model availability. Measured inference latency is reported but not applied to market fills.",
            "The app sends requests only to the endpoint you selected; no operator backend or model weights are included.",
        ],
        "discrepancy_summary": {
            "inference_rows": len(records),
            "positive_signal_negative_market_bar": sum(
                r["condition_matched"] and r["following_market_return"] < 0 for r in records
            ),
            "correct_external_forecast_negative_market_bar": sum(
                r["forecast_market_discrepancy"] for r in records
            ),
            "labeled_rows": len(labeled),
            "note": "Correct-forecast discrepancies require a known future target and a probability classifier. Following market moves are not per-trade realized P&L.",
        },
    }
