"""Small CPU-only, chronological supervised research with safe JSON models.

The model is deliberately modest: ridge regression on trailing features. It is a
working baseline for testing a research question, not evidence of a trading edge.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from .data import Bar
from .engine import Decision, ExecutionConfig, backtest

FEATURE_NAMES = (
    "return_1",
    "momentum_5",
    "sma_gap_10",
    "volatility_5",
    "volume_change",
)
MODEL_SCHEMA = "hypothesis-lab/ridge-v1"


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    number = _finite(value, name)
    if not number.is_integer() or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
    return int(number)


def trailing_features(bars: Sequence[Bar], index: int) -> dict[str, float]:
    """Compute inputs using bars through ``index`` only (ten-bar warmup)."""
    if index < 9 or index >= len(bars):
        raise ValueError("Features require an index with ten available bars")
    closes = [_finite(bar.close, "close") for bar in bars[index - 9 : index + 1]]
    volumes = [_finite(bar.volume, "volume") for bar in bars[index - 1 : index + 1]]
    if any(close <= 0 for close in closes) or any(volume < 0 for volume in volumes):
        raise ValueError("Features require positive closes and nonnegative volumes")
    returns = [closes[i] / closes[i - 1] - 1 for i in range(5, 10)]
    mean_return = sum(returns) / len(returns)
    return {
        "return_1": closes[-1] / closes[-2] - 1,
        "momentum_5": closes[-1] / closes[-6] - 1,
        "sma_gap_10": closes[-1] / (sum(closes) / len(closes)) - 1,
        "volatility_5": math.sqrt(sum((r - mean_return) ** 2 for r in returns) / 5),
        "volume_change": volumes[1] / volumes[0] - 1 if volumes[0] else 0.0,
    }


def _solve(matrix: list[list[float]], target: list[float]) -> list[float]:
    """Solve a small positive regularized system with partial pivoting."""
    size = len(target)
    augmented = [row[:] + [target[i]] for i, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-14:
            raise ValueError("Regression system is singular; use positive regularization")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        augmented[column] = [value / scale for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            multiplier = augmented[row][column]
            augmented[row] = [a - multiplier * b for a, b in zip(augmented[row], augmented[column])]
    return [augmented[row][-1] for row in range(size)]


def fit_ridge(
    features: Sequence[Sequence[float]],
    targets: Sequence[float],
    feature_names: Sequence[str] = FEATURE_NAMES,
    alpha: float = 1.0,
) -> dict[str, Any]:
    """Fit a numeric-only model; callers own chronological dataset separation."""
    names = list(feature_names)
    alpha = _finite(alpha, "alpha")
    if alpha <= 0:
        raise ValueError("alpha must be positive")
    if not names or any(not isinstance(name, str) for name in names):
        raise ValueError("Feature names must be supported strings")
    if len(set(names)) != len(names) or len(names) > 5:
        raise ValueError("Select one to five distinct supported features")
    if any(name not in FEATURE_NAMES for name in names):
        raise ValueError("Unsupported feature name")
    if len(features) != len(targets) or len(features) < 2:
        raise ValueError("At least two matching feature and target rows are required")
    width, count = len(names), len(features)
    x = [[_finite(value, "feature") for value in row] for row in features]
    y = [_finite(value, "target") for value in targets]
    if any(len(row) != width for row in x):
        raise ValueError("Feature rows must match the selected feature names")
    means = [sum(row[j] for row in x) / count for j in range(width)]
    scales = [
        math.sqrt(sum((row[j] - means[j]) ** 2 for row in x) / count) or 1.0 for j in range(width)
    ]
    normalized = [[(row[j] - means[j]) / scales[j] for j in range(width)] for row in x]
    intercept = sum(y) / count
    matrix = [
        [
            sum(row[j] * row[k] for row in normalized) + (alpha if j == k else 0)
            for k in range(width)
        ]
        for j in range(width)
    ]
    target = [
        sum(row[j] * (label - intercept) for row, label in zip(normalized, y)) for j in range(width)
    ]
    return {
        "schema": MODEL_SCHEMA,
        "family": "ridge",
        "feature_names": names,
        "means": means,
        "scales": scales,
        "coefficients": _solve(matrix, target),
        "intercept": intercept,
        "alpha": alpha,
        "training_rows": count,
    }


def predict(model: Mapping[str, Any], features: Mapping[str, float] | Sequence[float]) -> float:
    """Infer from a validated JSON model without loading executable objects."""
    if model.get("schema") != MODEL_SCHEMA or model.get("family") != "ridge":
        raise ValueError("Unsupported model schema or family")
    names = model.get("feature_names")
    if not isinstance(names, list) or not names or len(names) > len(FEATURE_NAMES):
        raise ValueError("Invalid model feature names")
    if any(not isinstance(name, str) for name in names):
        raise ValueError("Invalid model feature names")
    if len(set(names)) != len(names) or any(name not in FEATURE_NAMES for name in names):
        raise ValueError("Invalid model feature names")
    if isinstance(features, Mapping):
        try:
            values = [features[name] for name in names]
        except KeyError as exc:
            raise ValueError(f"Missing inference feature: {exc.args[0]}") from exc
    else:
        values = list(features)
    if len(values) != len(names):
        raise ValueError("Inference feature count does not match model")
    arrays: dict[str, list[float]] = {}
    for field in ("means", "scales", "coefficients"):
        raw = model.get(field)
        if not isinstance(raw, list) or len(raw) != len(names):
            raise ValueError(f"Invalid model {field}")
        arrays[field] = [_finite(value, field) for value in raw]
    if any(scale <= 0 for scale in arrays["scales"]):
        raise ValueError("Model scales must be positive")
    result = _finite(model.get("intercept"), "intercept") + sum(
        coefficient * (_finite(value, "feature") - mean) / scale
        for value, mean, scale, coefficient in zip(
            values, arrays["means"], arrays["scales"], arrays["coefficients"]
        )
    )
    return _finite(result, "prediction")


def _diagnostics(actual: list[float], predicted: list[float], baseline: float) -> dict[str, Any]:
    count = len(actual)
    residuals = [a - p for a, p in zip(actual, predicted)]
    squared = sum(residual * residual for residual in residuals)
    mean = sum(actual) / count
    total = sum((value - mean) ** 2 for value in actual)
    return {
        "rows": count,
        "mse": squared / count,
        "mae": sum(abs(residual) for residual in residuals) / count,
        "r2": 1 - squared / total if total > 0 else None,
        "directional_accuracy": sum((a > 0) == (p > 0) for a, p in zip(actual, predicted)) / count,
        "training_mean_baseline_mse": sum((a - baseline) ** 2 for a in actual) / count,
        "prediction_min": min(predicted),
        "prediction_max": max(predicted),
        "prediction_mean": sum(predicted) / count,
        "residual_mean": sum(residuals) / count,
    }


def _stamp(value: datetime) -> str:
    return value.isoformat()


def run_ml(bars: Sequence[Bar], config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Train on the past, select on validation, evaluate once on held-out data.

    Label: close[t+horizon]/close[t]-1. Trades enter at next open through the
    shared engine; prediction accuracy and strategy profitability are separate.
    """
    settings = dict(config or {})
    family = settings.get("model_family", "ridge")
    if family != "ridge":
        raise ValueError("This release supports the CPU ridge model family")
    horizon = _integer(settings.get("horizon", 1), "horizon", 1, 30)
    seed = _integer(settings.get("seed", 42), "seed", 0, 2**31 - 1)
    if len(bars) > 20000:
        raise ValueError("ML baseline is bounded to 20,000 bars per experiment")
    train_fraction = _finite(settings.get("train_fraction", 0.6), "train_fraction")
    validation_fraction = _finite(settings.get("validation_fraction", 0.2), "validation_fraction")
    if not 0 < train_fraction < 1 or not 0 < validation_fraction < 1:
        raise ValueError("Training and validation fractions must be between zero and one")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("Reserve a positive final test fraction")
    threshold = _finite(settings.get("threshold", 0.0), "threshold")
    raw_names = settings.get("feature_names", list(FEATURE_NAMES))
    if not isinstance(raw_names, (list, tuple)):
        raise ValueError("feature_names must be a list")
    names = list(raw_names)
    if not names or any(not isinstance(name, str) for name in names):
        raise ValueError("Feature names must be supported strings")
    if len(names) > 5 or len(set(names)) != len(names):
        raise ValueError("Select one to five distinct supported features")
    if any(name not in FEATURE_NAMES for name in names):
        raise ValueError("Unsupported feature name")
    raw_alphas = settings.get("ridge_alphas", [0.1, 1.0, 10.0])
    if not isinstance(raw_alphas, (list, tuple)) or not 1 <= len(raw_alphas) <= 20:
        raise ValueError("Choose one to twenty positive ridge_alphas")
    alphas = [_finite(alpha, "ridge alpha") for alpha in raw_alphas]
    if any(alpha <= 0 for alpha in alphas):
        raise ValueError("ridge_alphas must be positive")
    # Validate the complete chronological input, not only rows used as features.
    for i, bar in enumerate(bars):
        if not isinstance(bar.timestamp, datetime) or bar.timestamp.utcoffset() is None:
            raise ValueError("ML bars must have timezone-aware timestamps")
        if i and bar.timestamp <= bars[i - 1].timestamp:
            raise ValueError("ML bars must have strictly increasing timestamps")
        if _finite(bar.close, "close") <= 0 or _finite(bar.volume, "volume") < 0:
            raise ValueError("ML requires positive closes and nonnegative volume")
    indices = list(range(9, len(bars) - horizon))
    train_end = int(len(indices) * train_fraction)
    validation_end = int(len(indices) * (train_fraction + validation_fraction))
    if not 0 < train_end < validation_end < len(indices):
        raise ValueError("Not enough observations for three chronological periods")
    validation_start_index, test_start_index = indices[train_end], indices[validation_end]
    train = [index for index in indices[:train_end] if index + horizon < validation_start_index]
    validation = [
        index for index in indices[train_end:validation_end] if index + horizon < test_start_index
    ]
    test = indices[validation_end:]
    if len(train) < 12 or len(validation) < 6 or len(test) < 6:
        raise ValueError("Need at least 12 training, 6 validation and 6 test rows after purging")
    rows = {index: trailing_features(bars, index) for index in indices}
    labels = {
        index: _finite(bars[index + horizon].close / bars[index].close - 1, "target")
        for index in indices
    }
    training_x = [[rows[index][name] for name in names] for index in train]
    training_y = [labels[index] for index in train]
    candidates = []
    models = []
    for alpha in alphas:
        model = fit_ridge(training_x, training_y, names, alpha)
        predictions = [predict(model, rows[index]) for index in validation]
        diagnostics = _diagnostics(
            [labels[index] for index in validation], predictions, model["intercept"]
        )
        candidates.append({"alpha": alpha, "validation_mse": diagnostics["mse"]})
        models.append(model)
    selected = min(range(len(candidates)), key=lambda i: (candidates[i]["validation_mse"], i))
    model = models[selected]
    validation_predictions = [predict(model, rows[index]) for index in validation]
    test_predictions = [predict(model, rows[index]) for index in test]
    start, stop = test[0], test[-1] + horizon + 1
    market = list(bars[start:stop])
    decisions: list[Decision | None] = [None] * len(market)
    for index, prediction in zip(test, test_predictions):
        decisions[index - start] = Decision(target_weight=1.0 if prediction > threshold else 0.0)
    execution = ExecutionConfig(
        initial_cash=_finite(settings.get("initial_cash", 10000), "initial_cash"),
        fee_bps=_finite(settings.get("fee_bps", 10), "fee_bps"),
        slippage_bps=_finite(settings.get("slippage_bps", 5), "slippage_bps"),
        periods_per_year=_finite(settings.get("periods_per_year", 365), "periods_per_year"),
        bar_seconds=_finite(settings.get("bar_seconds", 86400), "bar_seconds"),
    )
    benchmark_decisions: list[Decision | None] = [Decision(target_weight=1.0)] + [None] * (
        len(market) - 1
    )
    strategy_result = backtest(market, decisions, execution)
    benchmark_result = backtest(market, benchmark_decisions, execution)

    def period(name: str, selected_indices: list[int]) -> dict[str, Any]:
        return {
            "name": name,
            "rows": len(selected_indices),
            "first_index": selected_indices[0],
            "last_index": selected_indices[-1],
            "last_label_index": selected_indices[-1] + horizon,
            "start": _stamp(bars[selected_indices[0]].timestamp),
            "end": _stamp(bars[selected_indices[-1]].timestamp),
            "label_end": _stamp(bars[selected_indices[-1] + horizon].timestamp),
        }

    model["horizon"] = horizon
    model["seed"] = seed
    model["training_end"] = _stamp(bars[train[-1] + horizon].timestamp)
    return {
        "mode": "ml",
        "model": model,
        "configuration": {
            "model_family": "ridge",
            "feature_names": names,
            "horizon": horizon,
            "train_fraction": train_fraction,
            "validation_fraction": validation_fraction,
            "ridge_alphas": alphas,
            "threshold": threshold,
            "seed": seed,
            "initial_cash": execution.initial_cash,
            "fee_bps": execution.fee_bps,
            "slippage_bps": execution.slippage_bps,
            "periods_per_year": execution.periods_per_year,
            "bar_seconds": execution.bar_seconds,
        },
        "target": f"close[t+{horizon}]/close[t]-1",
        "splits": {
            "train": period("train", train),
            "validation": period("validation", validation),
            "test": period("test", test),
            "purge_bars": horizon,
            "purged_rows": train_end - len(train) + validation_end - train_end - len(validation),
        },
        "search": {
            "objective": "minimum validation mean squared error",
            "trials": candidates,
            "trial_count": len(candidates),
            "selected_alpha": model["alpha"],
            "test_used_for_selection": False,
        },
        "validation": _diagnostics(
            [labels[index] for index in validation], validation_predictions, model["intercept"]
        ),
        "test": _diagnostics(
            [labels[index] for index in test], test_predictions, model["intercept"]
        ),
        "predictions": [
            {
                "timestamp": _stamp(bars[index].timestamp),
                "decision_at": _stamp(
                    bars[index].timestamp + timedelta(seconds=execution.bar_seconds)
                ),
                "index": index,
                "prediction": prediction,
                "actual": labels[index],
                "target_label_timestamp": _stamp(bars[index + horizon].timestamp),
                "target_label_available_at": _stamp(
                    bars[index + horizon].timestamp + timedelta(seconds=execution.bar_seconds)
                ),
                "decision": "long" if prediction > threshold else "cash",
            }
            for index, prediction in zip(test, test_predictions)
        ],
        "feature_diagnostics": [
            {"feature": name, "standardized_coefficient": coefficient}
            for name, coefficient in zip(names, model["coefficients"])
        ],
        "backtest": strategy_result,
        "benchmark": benchmark_result,
        "warnings": [
            "This is a small ridge baseline. Prediction accuracy does not establish profitability.",
            "Repeated searches on one validation period can overfit; reserve new future data.",
            "Overlapping horizon labels are correlated. No statistical significance is claimed.",
            "Standardized coefficients describe this fitted model, not causal effects.",
            "The prediction target is close-to-close; actual simulated trades fill at the next open.",
        ],
    }
