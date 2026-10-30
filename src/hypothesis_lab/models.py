"""Local tabular models and explicit inference-to-order rules.

The input matrix is already aligned point-in-time by the data layer. Models do
not fetch data, persist credentials or execute uploaded Python/pickle objects.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from typing import Any

from .data import Bar, timestamp, validate_bars
from .engine import Decision, ExecutionConfig, backtest, benchmark
from .ml import _solve

MODEL_SCHEMA = "hypothesis-lab/tabular-v1"
MAX_FEATURES = 32
MAX_ROWS = 5000
MAX_ONNX_BYTES = 5_000_000


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f"{name} must be a finite number") from None
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    number = _number(value, name)
    if not number.is_integer() or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
    return int(number)


def _names(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= MAX_FEATURES:
        raise ValueError("Select one to 32 named input features")
    names = list(value)
    if any(
        not isinstance(name, str) or not name.strip() or len(name) > 128 or "\x00" in name
        for name in names
    ):
        raise ValueError("Feature names must be nonempty strings of at most 128 characters")
    if len(set(names)) != len(names):
        raise ValueError("Feature names must be distinct")
    return names


def _feature_mapping(value: Any, model_names: Sequence[str]) -> dict[str, str]:
    if not isinstance(value, dict) or any(name not in model_names for name in value):
        raise ValueError("Feature mapping keys must name model inputs")
    if any(
        not isinstance(name, str) or not name.strip() or len(name) > 128 or "\x00" in name
        for name in value.values()
    ):
        raise ValueError("Feature mapping values must name nonempty local feature columns")
    return value.copy()


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1 / (1 + math.exp(-min(value, 700)))
    exponent = math.exp(max(value, -700))
    return exponent / (1 + exponent)


def fit_tabular(
    features: Sequence[Sequence[float]],
    targets: Sequence[float],
    feature_names: Sequence[str],
    *,
    family: str = "logistic",
    l2: float = 0.01,
    epochs: int = 250,
    learning_rate: float = 0.15,
) -> dict[str, Any]:
    """Fit ridge or binary logistic regression with training-only normalization."""
    names = _names(feature_names)
    if family not in {"ridge", "logistic"}:
        raise ValueError("Supported tabular model families are logistic and ridge")
    penalty = _number(l2, "Regularization")
    if penalty <= 0:
        raise ValueError("Regularization must be positive")
    count, width = len(features), len(names)
    if count != len(targets) or not 2 <= count <= MAX_ROWS:
        raise ValueError("Training requires two to 5,000 matching feature and target rows")
    x = [[_number(v, "Feature") for v in row] for row in features]
    y = [_number(v, "Target") for v in targets]
    if any(len(row) != width for row in x):
        raise ValueError("Training feature row width does not match its names")
    if family == "logistic" and any(v not in {0.0, 1.0} for v in y):
        raise ValueError("Logistic targets must be binary zero/one values")
    means = [sum(row[column] for row in x) / count for column in range(width)]
    scales = [
        math.sqrt(sum((row[column] - means[column]) ** 2 for row in x) / count) or 1
        for column in range(width)
    ]
    normalized = [
        [(row[column] - means[column]) / scales[column] for column in range(width)] for row in x
    ]
    if family == "ridge":
        intercept = sum(y) / count
        matrix = [
            [
                sum(row[j] * row[k] for row in normalized) + (penalty if j == k else 0)
                for k in range(width)
            ]
            for j in range(width)
        ]
        rhs = [
            sum(row[j] * (label - intercept) for row, label in zip(normalized, y))
            for j in range(width)
        ]
        coefficients = _solve(matrix, rhs)
    else:
        epochs = _integer(epochs, "Training epochs", 1, 2000)
        rate = _number(learning_rate, "Learning rate")
        if not 0 < rate <= 1:
            raise ValueError("Learning rate must be in (0,1]")
        if count * width * epochs > 25_000_000:
            raise ValueError("Training budget exceeded; reduce rows, features or epochs")
        prior = min(1 - 1e-6, max(1e-6, sum(y) / count))
        intercept = math.log(prior / (1 - prior))
        coefficients = [0.0] * width
        for _ in range(epochs):
            gradients = [0.0] * width
            bias_gradient = 0.0
            for row, label in zip(normalized, y):
                error = _sigmoid(intercept + sum(a * b for a, b in zip(coefficients, row))) - label
                bias_gradient += error
                for column in range(width):
                    gradients[column] += error * row[column]
            intercept -= rate * bias_gradient / count
            coefficients = [
                value - rate * (gradient / count + penalty * value)
                for value, gradient in zip(coefficients, gradients)
            ]
    model = {
        "schema": MODEL_SCHEMA,
        "family": family,
        "feature_names": names,
        "means": means,
        "scales": scales,
        "coefficients": coefficients,
        "intercept": intercept,
        "l2": penalty,
        "training_rows": count,
        "output_kind": "probability" if family == "logistic" else "prediction",
    }
    validate_model(model)
    return model


def validate_model(model: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a numeric JSON artifact; no executable serialization is accepted."""
    if not isinstance(model, Mapping) or model.get("schema") not in {
        MODEL_SCHEMA,
        "hypothesis-lab/ridge-v1",
    }:
        raise ValueError(
            "Unsupported model schema. Upload numeric Lab JSON or a configured ONNX model; pickle/joblib/Python is not loaded."
        )
    if model.get("family") not in {"ridge", "linear", "logistic"}:
        raise ValueError("JSON model family must be ridge, linear or logistic")
    names = _names(model.get("feature_names"))
    normalized = dict(model)
    normalized["feature_names"] = names
    for field in ("means", "scales", "coefficients"):
        raw = model.get(field)
        if not isinstance(raw, list) or len(raw) != len(names):
            raise ValueError(f"Model {field} must match feature_names")
        normalized[field] = [_number(value, f"Model {field}") for value in raw]
    if any(scale <= 0 for scale in normalized["scales"]):
        raise ValueError("Model scales must be positive")
    normalized["intercept"] = _number(model.get("intercept"), "Model intercept")
    normalized["output_kind"] = "probability" if model["family"] == "logistic" else "prediction"
    if model.get("trained_through") is not None:
        normalized["trained_through"] = timestamp(model["trained_through"]).isoformat()
    return normalized


def predict_tabular(model: Mapping[str, Any], row: Mapping[str, Any] | Sequence[float]) -> float:
    validated = validate_model(model)
    names = validated["feature_names"]
    if isinstance(row, Mapping):
        if any(name not in row or row[name] is None for name in names):
            raise ValueError("Inference row is missing a configured model input")
        values = [row[name] for name in names]
    else:
        values = list(row)
    if len(values) != len(names):
        raise ValueError("Inference row width differs from the model inputs")
    score = validated["intercept"] + sum(
        coefficient * (_number(value, "Inference feature") - mean) / scale
        for coefficient, value, mean, scale in zip(
            validated["coefficients"], values, validated["means"], validated["scales"]
        )
    )
    result = _sigmoid(score) if validated["family"] == "logistic" else score
    return _number(result, "Prediction")


def _onnx_session(artifact: Mapping[str, Any]):
    try:
        import onnxruntime as ort
    except ImportError:
        raise ValueError(
            "ONNX inference is optional. Install hypothesis-lab[onnx] on your own computer, then restart the local app."
        ) from None
    local_path = artifact.get("model_path")
    if local_path:
        path = Path(local_path)
        if (
            artifact.get("allow_local_file") is not True
            or not path.is_absolute()
            or path.suffix.lower() != ".onnx"
            or not path.is_file()
        ):
            raise ValueError(
                "Choose an existing absolute .onnx path and explicitly allow the local runtime to read it"
            )
        if path.stat().st_size > 2_000_000_000:
            raise ValueError(
                "This local ONNX adapter limits the main graph file to 2 GB; use your own inference endpoint for larger models"
            )
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.log_severity_level = 4
        try:
            session = ort.InferenceSession(
                str(path), sess_options=options, providers=["CPUExecutionProvider"]
            )
        except Exception:
            raise ValueError(
                "The selected local ONNX model could not be loaded. Verify model files, runtime support and available memory."
            ) from None
        if (
            len(session.get_inputs()) != 1
            or session.get_inputs()[0].type not in {"tensor(float)", "tensor(double)"}
            or len(session.get_inputs()[0].shape) != 2
        ):
            raise ValueError(
                "This adapter needs one numeric [batch,features] ONNX input; other models can use a user-controlled endpoint"
            )
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1_048_576), b""):
                digest.update(chunk)
        return session, digest.hexdigest()
    encoded = artifact.get("data_base64")
    if not isinstance(encoded, str) or len(encoded) > MAX_ONNX_BYTES * 4 / 3 + 8:
        raise ValueError("ONNX upload must be at most 5 MB")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("Invalid ONNX upload encoding") from None
    if not raw or len(raw) > MAX_ONNX_BYTES:
        raise ValueError("ONNX upload must be nonempty and at most 5 MB")
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    options.log_severity_level = 4
    try:
        session = ort.InferenceSession(
            raw, sess_options=options, providers=["CPUExecutionProvider"]
        )
    except Exception:
        raise ValueError(
            "The ONNX graph could not be loaded locally. Use a self-contained model supported by ONNX Runtime; external data files and custom Python operators are not loaded."
        ) from None
    if len(session.get_inputs()) != 1:
        raise ValueError("This adapter supports one numeric [batch,features] ONNX input")
    input_info = session.get_inputs()[0]
    if input_info.type not in {"tensor(float)", "tensor(double)"} or len(input_info.shape) != 2:
        raise ValueError("ONNX input must be a float32/float64 [batch,features] matrix")
    return session, hashlib.sha256(raw).hexdigest()


def inspect_uploaded(artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Report supported model inputs/outputs without storing an upload."""
    if artifact.get("format") == "onnx":
        session, model_hash = _onnx_session(artifact)
        return {
            "format": "onnx",
            "family": "onnx",
            "sha256": model_hash,
            "inputs": [
                {"name": value.name, "shape": value.shape, "type": value.type}
                for value in session.get_inputs()
            ],
            "outputs": [
                {"name": value.name, "shape": value.shape, "type": value.type}
                for value in session.get_outputs()
            ],
            "warning": "Pretraining data/provenance is user supplied. Map feature order and probability output explicitly.",
        }
    model = artifact.get("model", artifact)
    validated = validate_model(model)
    return {
        "format": "json",
        "family": validated["family"],
        "feature_names": validated["feature_names"],
        "output_kind": validated["output_kind"],
        "trained_through": validated.get("trained_through"),
        "model": validated,
    }


def infer_uploaded(
    artifact: Mapping[str, Any],
    rows: list[dict[str, float]],
    config: Mapping[str, Any] | None = None,
) -> tuple[list[float], dict[str, Any]]:
    """Infer locally from numeric JSON or an optional portable ONNX tensor graph."""
    settings = dict(config or {})
    if not rows or len(rows) > MAX_ROWS:
        raise ValueError("Inference requires one to 5,000 rows")
    if artifact.get("format") != "onnx":
        model = validate_model(artifact.get("model", artifact))
        mapping = _feature_mapping(settings.get("feature_mapping", {}), model["feature_names"])
        mapped = [
            {name: row.get(mapping.get(name, name)) for name in model["feature_names"]}
            for row in rows
        ]
        predictions = [predict_tabular(model, row) for row in mapped]
        return predictions, model
    session, model_hash = _onnx_session(artifact)
    import numpy as np

    names = _names(settings.get("feature_names", artifact.get("feature_names")))
    input_info = session.get_inputs()[0]
    if isinstance(input_info.shape[1], int) and input_info.shape[1] != len(names):
        raise ValueError("ONNX feature count does not match the uploaded input tensor")
    output_name = settings.get("output_name", artifact.get("output_name"))
    available = [info.name for info in session.get_outputs()]
    if output_name is None and len(available) == 1:
        output_name = available[0]
    if output_name not in available:
        raise ValueError("Choose an exact ONNX output name from the inspected model")
    kind = settings.get("output_kind", artifact.get("output_kind", "probability"))
    if kind not in {"probability", "prediction"}:
        raise ValueError("Output kind must be probability or prediction")
    matrix = np.asarray(
        [[_number(row.get(name), "Mapped ONNX feature") for name in names] for row in rows],
        dtype=np.float32 if input_info.type == "tensor(float)" else np.float64,
    )
    try:
        # A fixed-size model can still be evaluated safely one observation at a time.
        batch = input_info.shape[0]
        if isinstance(batch, int) and batch not in {1, len(rows)}:
            raise ValueError("ONNX batch dimension must be dynamic, one, or match the input rows")
        chunks = [matrix[i : i + 1] for i in range(len(rows))] if batch == 1 else [matrix]
        values = [
            np.asarray(session.run([output_name], {input_info.name: chunk})[0]) for chunk in chunks
        ]
        output = np.concatenate(values, axis=0) if len(values) > 1 else values[0]
    except ValueError:
        raise
    except Exception:
        raise ValueError("ONNX inference failed for the configured tensor inputs/output") from None
    if output.ndim == 2:
        column = _integer(
            settings.get(
                "output_column", artifact.get("output_column", 1 if output.shape[1] == 2 else 0)
            ),
            "Output column",
            0,
            63,
        )
        if output.shape[1] > 64 or column >= output.shape[1]:
            raise ValueError("Output column does not exist in a bounded numeric tensor")
        output = output[:, column]
    if output.ndim != 1 or output.shape[0] != len(rows):
        raise ValueError(
            "Selected ONNX output must contain one scalar per observation (ZipMap/sequence outputs are unsupported)"
        )
    predictions = [_number(value, "ONNX output") for value in output.tolist()]
    if kind == "probability" and any(not 0 <= value <= 1 for value in predictions):
        raise ValueError(
            "Selected probability output is outside [0,1]; choose the correct output or use prediction output kind"
        )
    return predictions, {
        "schema": "hypothesis-lab/onnx-descriptor-v1",
        "family": "onnx",
        "feature_names": names,
        "output_kind": kind,
        "output_name": output_name,
        "output_column": settings.get("output_column", artifact.get("output_column")),
        "sha256": model_hash,
        "trained_through": settings.get("trained_through", artifact.get("trained_through")),
    }


def _decision_config(settings: Mapping[str, Any], kind: str) -> dict[str, Any]:
    raw = settings.get("decision", {})
    if not isinstance(raw, Mapping):
        raise ValueError("Decision policy must be an object")
    comparison = raw.get("comparison", ">")
    if comparison not in {">", ">=", "<", "<=", "=="}:
        raise ValueError("Decision comparison must be >, >=, <, <= or ==")
    threshold = _number(
        raw.get("threshold", settings.get("threshold", 0.5 if kind == "probability" else 0)),
        "Decision threshold",
    )
    if kind == "probability" and not 0 <= threshold <= 1:
        raise ValueError("A probability threshold must be in [0,1]")
    when_true = raw.get("when_true", {"target_weight": 1.0})
    if not isinstance(when_true, Mapping) or set(when_true) not in (
        {"target_weight"},
        {"buy_cash"},
    ):
        raise ValueError(
            "True decision must specify target_weight or a fee-inclusive buy_cash budget"
        )
    when_true = {key: _number(value, "Decision sizing") for key, value in when_true.items()}
    Decision(**when_true)
    when_false = raw.get("when_false", "exit")
    if when_false not in {"exit", "hold"}:
        raise ValueError("False decision must be exit or hold")
    return {
        "output_kind": kind,
        "comparison": comparison,
        "threshold": threshold,
        "when_true": when_true,
        "when_false": when_false,
    }


def prediction_decision(value: float, policy: Mapping[str, Any]) -> tuple[Decision | None, bool]:
    number = _number(value, "Inference output")
    if policy["output_kind"] == "probability" and not 0 <= number <= 1:
        raise ValueError("Probability output must be in [0,1]")
    threshold = policy["threshold"]
    matched = {
        ">": number > threshold,
        ">=": number >= threshold,
        "<": number < threshold,
        "<=": number <= threshold,
        "==": number == threshold,
    }[policy["comparison"]]
    if matched:
        return Decision(**policy["when_true"]), True
    return (Decision(target_weight=0) if policy["when_false"] == "exit" else None), False


def _diagnostics(
    actual: list[float], predictions: list[float], kind: str, baseline: float | None = None
) -> dict[str, Any]:
    if not actual:
        return {"rows": 0, "mse": None, "mae": None, "directional_accuracy": None}
    count = len(actual)
    mse = sum((a - p) ** 2 for a, p in zip(actual, predictions)) / count
    result: dict[str, Any] = {
        "rows": count,
        "mse": mse,
        "mae": sum(abs(a - p) for a, p in zip(actual, predictions)) / count,
        "prediction_mean": sum(predictions) / count,
        "prediction_min": min(predictions),
        "prediction_max": max(predictions),
        "residual_mean": sum(a - p for a, p in zip(actual, predictions)) / count,
    }
    if baseline is not None:
        result["training_mean_baseline_mse"] = sum((a - baseline) ** 2 for a in actual) / count
    if kind == "probability":
        clipped = [min(1 - 1e-12, max(1e-12, p)) for p in predictions]
        result.update(
            {
                "log_loss": -sum(
                    a * math.log(p) + (1 - a) * math.log(1 - p) for a, p in zip(actual, clipped)
                )
                / count,
                "brier_score": mse,
                "accuracy": sum((a == 1) == (p > 0.5) for a, p in zip(actual, predictions)) / count,
                "directional_accuracy": sum(
                    (a == 1) == (p > 0.5) for a, p in zip(actual, predictions)
                )
                / count,
                "confusion_matrix": [
                    [
                        sum(
                            a == expected and (p > 0.5) == bool(predicted)
                            for a, p in zip(actual, predictions)
                        )
                        for predicted in (0, 1)
                    ]
                    for expected in (0, 1)
                ],
            }
        )
    else:
        mean = sum(actual) / count
        total = sum((a - mean) ** 2 for a in actual)
        result["r2"] = 1 - mse * count / total if total > 0 else None
        result["directional_accuracy"] = (
            sum((a > 0) == (p > 0) for a, p in zip(actual, predictions)) / count
        )
    return result


def run_tabular_model(
    bars: list[Bar],
    feature_rows: list[dict[str, float | None]],
    config: Mapping[str, Any] | None = None,
    pretrained: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Train or evaluate an uploaded model using aligned arbitrary numeric fields.

    An external target is defined from its point-in-time aligned values at t and
    t+horizon. That target need not be a market price or return. Profitability is
    evaluated separately through the shared execution engine.
    """
    validate_bars(bars)
    if len(feature_rows) != len(bars) or len(bars) > MAX_ROWS:
        raise ValueError("Provide one aligned feature row per market bar, at most 5,000")
    if any(not isinstance(row, Mapping) for row in feature_rows):
        raise ValueError("Aligned feature rows must be named-column objects")
    settings = dict(config or {})
    horizon = _integer(settings.get("horizon", 1), "Forecast horizon", 1, 30)
    target_field = settings.get("target_field", "market.close")
    if not isinstance(target_field, str) or not target_field:
        raise ValueError("Target field must name a market or external numeric column")
    target_type = settings.get("target_type", "increase")
    if target_type not in {"increase", "return", "level", "condition"}:
        raise ValueError("Target type must be increase, return, level or condition")
    binary_target = target_type in {"increase", "condition"}
    condition_values = None
    if target_type == "condition":
        from .algorithms import SignalInterpreter

        condition_values = SignalInterpreter(feature_rows).run(settings.get("target_condition", ""))
        if any(value is not None and not isinstance(value, bool) for value in condition_values):
            raise ValueError("Target condition must produce boolean outcomes; use a comparison")
    execution = ExecutionConfig(
        **{
            name: _number(settings.get(name, value), name)
            for name, value in asdict(ExecutionConfig()).items()
        }
    )
    train_fraction = _number(settings.get("train_fraction", 0.6), "Training fraction")
    val_fraction = _number(settings.get("validation_fraction", 0.2), "Validation fraction")
    if not 0 < train_fraction < 1 or not 0 < val_fraction < 1 or train_fraction + val_fraction >= 1:
        raise ValueError("Reserve positive chronological training, validation and test periods")
    mapping = settings.get("feature_mapping", {})
    if not isinstance(mapping, dict):
        raise ValueError("Feature mapping must be an object")
    if pretrained and pretrained.get("format") != "onnx":
        uploaded = validate_model(pretrained.get("model", pretrained))
        mapping = _feature_mapping(mapping, uploaded["feature_names"])
        names = _names([mapping.get(name, name) for name in uploaded["feature_names"]])
        model_names = uploaded["feature_names"]
    else:
        names = _names(
            settings.get("feature_names", pretrained.get("feature_names") if pretrained else None)
        )
        model_names = names
    all_names = set().union(*(row.keys() for row in feature_rows))
    if any(name not in all_names for name in names):
        raise ValueError("A selected model input is absent from the aligned dataset")
    if (
        target_type != "condition"
        and target_field != "market.close"
        and target_field not in all_names
    ):
        raise ValueError("Selected target field is absent from the aligned dataset")
    rows: dict[int, dict[str, float]] = {}
    for index, raw in enumerate(feature_rows):
        if any(raw.get(name) is None for name in names):
            continue
        rows[index] = {name: _number(raw[name], f"Feature {name}") for name in names}

    def target_value(index: int) -> float | None:
        raw = (
            bars[index].close
            if target_field == "market.close"
            else feature_rows[index].get(target_field)
        )
        return None if raw is None else _number(raw, "Target value")

    labels = {}
    for index in range(len(bars) - horizon):
        if condition_values is not None:
            future_condition = condition_values[index + horizon]
            if future_condition is not None:
                labels[index] = float(future_condition)
            continue
        current, future = target_value(index), target_value(index + horizon)
        if current is None or future is None:
            continue
        if target_type == "increase":
            labels[index] = float(future > current)
        elif target_type == "level":
            labels[index] = future
        elif current != 0:
            labels[index] = _number(future / current - 1, "Target return")
    train_boundary = int(len(bars) * train_fraction)
    test_boundary = int(len(bars) * (train_fraction + val_fraction))
    eligible = sorted(set(rows).intersection(labels))
    train = [i for i in eligible if i + horizon < train_boundary]
    validation = [i for i in eligible if train_boundary <= i and i + horizon < test_boundary]
    test = [i for i in eligible if i >= test_boundary]
    warnings = [
        "Alternative-data predictions and market profitability are separate hypotheses. A correct forecast does not imply a profitable trade.",
        "Aligned inputs must contain historically available values only. This model layer cannot verify the truth of user-supplied timestamps or pretraining claims.",
        "Repeated validation searches and overlapping targets can overfit. No predictive edge or statistical significance is claimed.",
    ]
    if len(rows) < len(bars):
        warnings.append(
            f"{len(bars) - len(rows)} rows with missing configured inputs are not used for training/inference. Missing inference keeps the previous portfolio exposure."
        )
    if pretrained:
        start = _integer(
            settings.get("evaluation_start_index", test_boundary),
            "Evaluation start",
            0,
            len(bars) - 2,
        )
        inference_indices = [index for index in sorted(rows) if start <= index < len(bars) - 1]
        if not inference_indices:
            raise ValueError(
                "No complete feature rows exist in the uploaded model's evaluation period"
            )
        predictions, model = infer_uploaded(
            pretrained, [rows[index] for index in inference_indices], settings
        )
        kind = model["output_kind"]
        trained_through = settings.get(
            "trained_through", model.get("trained_through", model.get("training_end"))
        )
        if trained_through:
            trained_at = timestamp(trained_through)
            first_decision = bars[inference_indices[0]].timestamp + timedelta(
                seconds=execution.bar_seconds
            )
            if trained_at >= first_decision:
                raise ValueError(
                    "The declared model training period overlaps evaluation; choose a later evaluation start"
                )
            warnings.append(
                "Uploaded model pretraining dates are user declarations; their datasets, preprocessing and independence have not been independently audited."
            )
        else:
            warnings.append(
                "Uploaded model training provenance is unknown: this is a historical inference replay, not a verified out-of-sample performance claim."
            )
        search = {
            "objective": "none: uploaded model inference only",
            "trials": [],
            "trial_count": 0,
            "selected_alpha": None,
            "test_used_for_selection": False,
        }
        validation_predictions: list[float] = []
        evaluated_validation: list[int] = []
        test = [i for i in inference_indices if i in labels]
        train, validation = [], []
        baseline = None
    else:
        if len(train) < 12 or len(validation) < 6 or len(test) < 6:
            raise ValueError(
                "Need at least 12 train, 6 validation and 6 test rows after missing-value filtering and horizon purging"
            )
        family = settings.get("model_family", "logistic" if binary_target else "ridge")
        if binary_target != (family == "logistic"):
            raise ValueError(
                "Use logistic for an increase probability, or ridge for a future level/return"
            )
        l2_values = settings.get("l2_candidates", [0.001, 0.01, 0.1])
        if not isinstance(l2_values, (list, tuple)) or not 1 <= len(l2_values) <= 8:
            raise ValueError("Choose one to eight positive regularization candidates")
        penalties = [_number(value, "Regularization") for value in l2_values]
        epochs = _integer(settings.get("epochs", 250), "Training epochs", 1, 2000)
        if family == "logistic" and len(train) * len(names) * epochs * len(penalties) > 40_000_000:
            raise ValueError(
                "Search training budget exceeded; reduce candidates, epochs, rows or features"
            )
        x = [[rows[index][name] for name in names] for index in train]
        y = [labels[index] for index in train]
        fitted, trials = [], []
        kind = "probability" if family == "logistic" else "prediction"
        objective = "log_loss" if kind == "probability" else "mse"
        for penalty in penalties:
            candidate = fit_tabular(
                x,
                y,
                model_names,
                family=family,
                l2=penalty,
                epochs=epochs,
                learning_rate=settings.get("learning_rate", 0.15),
            )
            predictions = [
                predict_tabular(candidate, [rows[index][name] for name in names])
                for index in validation
            ]
            scores = _diagnostics([labels[index] for index in validation], predictions, kind)
            fitted.append(candidate)
            trials.append({"l2": penalty, "validation_objective": scores[objective]})
        selected = min(
            range(len(trials)), key=lambda index: (trials[index]["validation_objective"], index)
        )
        model = fitted[selected]
        model.update(
            {
                "target_field": target_field,
                "target_type": target_type,
                **(
                    {"target_condition": settings["target_condition"]}
                    if target_type == "condition"
                    else {}
                ),
                "horizon": horizon,
                "trained_through": (
                    bars[train[-1] + horizon].timestamp
                    + timedelta(seconds=execution.bar_seconds + execution.data_delay_ms / 1000)
                ).isoformat(),
            }
        )
        inference_indices = test
        predictions = [
            predict_tabular(model, [rows[index][name] for name in names])
            for index in inference_indices
        ]
        validation_predictions = [
            predict_tabular(model, [rows[index][name] for name in names]) for index in validation
        ]
        evaluated_validation = validation
        baseline = sum(y) / len(y)
        search = {
            "objective": f"minimum validation {objective}",
            "trials": trials,
            "trial_count": len(trials),
            "selected_alpha": model["l2"],
            "test_used_for_selection": False,
        }
        start = test_boundary
        if kind == "probability" and len(set(y)) < 2:
            warnings.append(
                "The training target contains only one class; probability estimates cannot learn a class distinction in this period."
            )
    if kind == "probability" and not binary_target:
        warnings.append(
            "Probability output is being compared against a non-binary target. Configure an increase target for classification diagnostics."
        )
    policy = _decision_config(settings, kind)
    market = bars[start:]
    decisions: list[Decision | None] = [None] * len(market)
    prediction_map = dict(zip(inference_indices, predictions))
    decision_records: list[dict[str, Any]] = []
    for index in inference_indices:
        decision, matched = prediction_decision(prediction_map[index], policy)
        decisions[index - start] = decision
        following = bars[index + 1]
        decision_records.append(
            {
                "timestamp": bars[index].timestamp.isoformat(),
                "decision_at": (
                    bars[index].timestamp
                    + timedelta(seconds=execution.bar_seconds + execution.data_delay_ms / 1000)
                ).isoformat(),
                "index": index,
                "bar_index": index,
                "features": rows[index],
                "prediction": prediction_map[index],
                "probability": prediction_map[index] if kind == "probability" else None,
                "actual": labels.get(index),
                "target_label_timestamp": bars[index + horizon].timestamp.isoformat()
                if index + horizon < len(bars)
                else None,
                "target_label_available_at": (
                    bars[index + horizon].timestamp
                    + timedelta(seconds=execution.bar_seconds + execution.data_delay_ms / 1000)
                ).isoformat()
                if index + horizon < len(bars)
                else None,
                "condition_matched": matched,
                "decision": "long"
                if matched
                else "cash"
                if policy["when_false"] == "exit"
                else "hold",
                "intent": asdict(decision) if decision else None,
                "following_market_return": following.close / following.open - 1,
                "following_close_return": following.close / bars[index].close - 1,
                "forecast_correct": ((prediction_map[index] > 0.5) == bool(labels[index]))
                if kind == "probability" and binary_target and index in labels
                else None,
            }
        )
    strategy_result = backtest(market, decisions, execution)
    base = benchmark(market, execution)
    fills_by_decision: dict[str, list[dict]] = {}
    for fill in strategy_result["fills"]:
        fills_by_decision.setdefault(fill["decision_bar_open"], []).append(fill)
    order_by_bar = {item["submitted_bar"]: item for item in strategy_result["orders"]}
    for record in decision_records:
        record["fills"] = fills_by_decision.get(record["timestamp"], [])
        record["execution_status"] = order_by_bar.get(record["index"] - start, {}).get(
            "status", "hold"
        )
        record["forecast_market_discrepancy"] = bool(
            record["forecast_correct"]
            and record["condition_matched"]
            and record["following_market_return"] < 0
        )
    actual_indices = [i for i in inference_indices if i in labels]
    target_kind = "probability" if kind == "probability" and binary_target else "prediction"
    test_scores = _diagnostics(
        [labels[index] for index in actual_indices],
        [prediction_map[index] for index in actual_indices],
        target_kind,
        baseline,
    )
    if binary_target and kind != "probability":
        warnings.append(
            "Uploaded numeric scores are not calibrated probabilities. Increase-target diagnostics use residual error, not probability log loss or classification accuracy."
        )
        test_scores.pop("directional_accuracy", None)

    def period(name: str, indices: list[int]) -> dict[str, Any]:
        if not indices:
            return {
                "name": name,
                "rows": 0,
                "first_index": None,
                "last_index": None,
                "last_label_index": None,
                "start": None,
                "end": None,
                "label_end": None,
            }
        first, last = indices[0], indices[-1]
        return {
            "name": name,
            "rows": len(indices),
            "first_index": first,
            "last_index": last,
            "last_label_index": last + horizon,
            "start": bars[first].timestamp.isoformat(),
            "end": bars[last].timestamp.isoformat(),
            "label_end": bars[min(last + horizon, len(bars) - 1)].timestamp.isoformat(),
        }

    return {
        "mode": "tabular-model",
        "model": model,
        "configuration": {
            **settings,
            "feature_names": names,
            "target_field": target_field,
            "target_type": target_type,
            "horizon": horizon,
            "decision": policy,
            "evaluation_start_index": start,
            **asdict(execution),
        },
        "target": f"condition at t+{horizon}: {settings['target_condition']}"
        if target_type == "condition"
        else f"{target_field}[t+{horizon}] {'>' if target_type == 'increase' else '/ current - 1' if target_type == 'return' else 'future level'} {target_field}[t]"
        if target_type != "level"
        else f"{target_field}[t+{horizon}]",
        "splits": {
            "train": period("train", train),
            "validation": period("validation", validation),
            "test": period("test", actual_indices),
            "purge_bars": 0 if pretrained else horizon,
            "purged_rows": 0
            if pretrained
            else len(
                [
                    i
                    for i in eligible
                    if i < train_boundary <= i + horizon
                    or train_boundary <= i < test_boundary <= i + horizon
                ]
            ),
        },
        "search": search,
        "validation": _diagnostics(
            [labels[index] for index in evaluated_validation],
            validation_predictions,
            target_kind,
            baseline,
        ),
        "test": test_scores,
        "predictions": decision_records,
        "inference_decisions": decision_records,
        "feature_diagnostics": [
            {"feature": name, "standardized_coefficient": coefficient}
            for name, coefficient in zip(
                model.get("feature_names", []), model.get("coefficients", [])
            )
        ],
        "backtest": strategy_result,
        "benchmark": base,
        "warnings": warnings,
        "discrepancy_summary": {
            "inference_rows": len(decision_records),
            "unfilled_or_no_change": sum(
                record["execution_status"] != "filled" for record in decision_records
            ),
            "correct_external_forecast_negative_market_bar": sum(
                record["forecast_market_discrepancy"] for record in decision_records
            ),
            "note": "Discrepancy flags compare an external forecast with the following market open-to-close move. They are diagnostics, not per-trade realized P&L or proof of causality.",
        },
    }
