"""Research orchestration, explicit dataset provenance and comparison."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import random
from dataclasses import asdict

from .data import fingerprint, fixtures, load_bars, load_events
from .engine import ExecutionConfig, backtest, benchmark
from .features import align_features, as_events, demo_content, derive_features, prepare_dataset
from .local_inference import public_connection
from .storage import describe_experiment, save_experiment
from .strategies import decisions_for, preset


def run_experiment(payload: dict, *, persist: bool = True) -> dict:
    bars, events = fixtures()
    source = "Bundled synthetic demonstration; not Bitcoin market history"
    if payload.get("market_csv"):
        bars = load_bars(payload["market_csv"], content=True)
        # Never silently combine unrelated synthetic weather with user market data.
        events = []
        source = "User-imported CSV; user supplies provenance and usage rights"
    if payload.get("events_csv"):
        events = load_events(payload["events_csv"], content=True)
    if len(bars) > 5000:
        raise ValueError(
            "Interactive research is limited to 5,000 bars; use the Python API for larger datasets"
        )
    cfg_data = payload.get("execution", {})
    allowed = set(ExecutionConfig.__dataclass_fields__)
    if not isinstance(cfg_data, dict) or set(cfg_data) - allowed:
        raise ValueError("Unknown execution setting")
    cfg = ExecutionConfig(
        **{k: float(v) for k, v in {**asdict(ExecutionConfig()), **cfg_data}.items()}
    )
    feature_data = payload.get("feature_data", "")
    feature_format = payload.get("feature_format", "csv")
    feature_info = None
    feature_mapping = payload.get("feature_mapping", {})
    transforms = payload.get("transforms", [])
    if payload.get("mode") in {"model", "endpoint"} and not feature_data:
        feature_data = demo_content()
    if feature_data:
        observations, feature_info = prepare_dataset(feature_data, feature_format, feature_mapping)
        feature_mapping = feature_info["mapping"]
        aligned = derive_features(
            align_features(bars, observations, feature_info, cfg.bar_seconds), transforms
        )
        events = (
            load_events(payload["events_csv"], content=True) if payload.get("events_csv") else []
        ) + as_events(observations)
        # Derived features become available only at the decision close that computed them.
        if transforms:
            from datetime import timedelta

            from .data import Event

            for i, row in enumerate(aligned):
                when = bars[i].timestamp + timedelta(seconds=cfg.bar_seconds)
                for transform in transforms:
                    name = transform["name"]
                    value = row.get(name)
                    if value is not None:
                        events.append(Event(when, when, value, name, "Feature table"))
    mode = payload.get("mode", "rules")
    spec = dict(payload.get("strategy") or preset("weather", slow=200))
    if feature_info:
        # One visible expiry policy applies to both rule and model workflows.
        spec["event_max_age_hours"] = feature_info["mapping"]["max_age_hours"]
    if mode in {"model", "endpoint"}:
        assert feature_info is not None
        config = {**payload.get("model_config", {}), **asdict(cfg)}
        if not config.get("feature_names"):
            config["feature_names"] = feature_info["generated_fields"][:5]
        pretrained = payload.get("pretrained")
        if pretrained and pretrained.get("feature_mapping"):
            config["feature_mapping"] = pretrained["feature_mapping"]
        if mode == "endpoint":
            from .local_inference import run_endpoint_model

            result = run_endpoint_model(
                bars,
                aligned,
                config,
                payload.get("connection", {}),
                payload.get("model_credential"),
            )
        else:
            from .models import run_tabular_model

            result = run_tabular_model(bars, aligned, config, pretrained)
        strategy, base = result["backtest"], result["benchmark"]
    elif mode == "ml":
        from .ml import run_ml

        ml_config = {**payload.get("ml", {}), **asdict(cfg)}
        result = run_ml(bars, ml_config)
        strategy, base = result["backtest"], result["benchmark"]
    elif mode == "rules":
        if float(spec.get("bar_seconds", cfg.bar_seconds)) != cfg.bar_seconds:
            raise ValueError("Strategy and execution bar duration must agree")
        result = {}
        runtime_spec = {**spec, "_aligned_features": aligned} if feature_info else spec
        strategy = backtest(bars, decisions_for(bars, runtime_spec, events), cfg)
        base = benchmark(bars, cfg)
    else:
        raise ValueError("Supported application modes are rules, ml, model and endpoint")
    excess = strategy["metrics"]["total_return"] - base["metrics"]["total_return"]
    record = {
        "schema_version": 1,
        "mode": mode,
        "name": str(payload.get("name") or spec.get("name") or "Research experiment")[:100],
        "dataset": {
            "identity": hashlib.sha256(
                (
                    fingerprint(bars, events)
                    + json.dumps(feature_mapping, sort_keys=True)
                    + json.dumps(transforms, sort_keys=True)
                    + hashlib.sha256(feature_data.encode()).hexdigest()
                ).encode()
            ).hexdigest()
            if feature_data
            else fingerprint(bars, events),
            "source": source,
            "rows": len(bars),
            "start": bars[0].timestamp.isoformat(),
            "end": bars[-1].timestamp.isoformat(),
            "location": spec.get("location"),
            "provenance_note": str(payload.get("provenance_note", ""))[:1000],
        },
        "configuration": {
            "strategy": spec,
            "execution": asdict(cfg),
            "ml": payload.get("ml", {}),
            "feature_mapping": feature_mapping,
            "model_config": result.get("configuration", payload.get("model_config", {})),
            "transforms": transforms,
            "connection": public_connection(
                payload.get("connection", {}), payload.get("model_credential")
            ),
        },
        "inputs": {
            "market_csv": payload.get("market_csv", ""),
            "events_csv": payload.get("events_csv", ""),
            "feature_data": feature_data,
            "feature_format": feature_format,
            "pretrained": payload.get("pretrained"),
        },
        "strategy": strategy,
        "benchmark": base,
        "ml": result if mode == "ml" else None,
        "model": result if mode in {"model", "endpoint"} else None,
        "market": [{**asdict(bar), "timestamp": bar.timestamp.isoformat()} for bar in bars],
        "ledger": strategy["equity"],
        "feature_dataset": feature_info,
        "diagnostics": {
            "inference_decisions": result.get("inference_decisions", result.get("predictions", [])),
            "discrepancies": result.get("discrepancy_summary", {}),
        },
        "summary": {**strategy["metrics"], "excess_return": excess},
        "warnings": strategy["warnings"]
        + [
            "Exploratory comparisons do not prove a predictive edge. Repeated selection increases false discoveries."
        ],
    }
    if not payload.get("market_csv"):
        record["warnings"].append(
            "Synthetic fixtures are for software demonstration only; results are not market performance."
        )
    if mode in {"ml", "model", "endpoint"}:
        record["warnings"].extend(result.get("warnings", []))
    if feature_info:
        record["warnings"].extend(feature_info["warnings"])
        record["dataset"]["feature_fields"] = feature_info["generated_fields"]
    return save_experiment(record) if persist else describe_experiment(record)


def rerun_payload(record: dict) -> dict:
    if record.get("schema_version") != 1:
        raise ValueError("Unsupported experiment schema version")
    config = record["configuration"]
    return {
        "mode": record["mode"],
        "name": record.get("name"),
        "strategy": config["strategy"],
        "execution": config["execution"],
        "ml": config.get("ml", {}),
        "feature_mapping": config.get("feature_mapping", {}),
        "model_config": config.get("model_config", {}),
        "transforms": config.get("transforms", []),
        "connection": config.get("connection", {}),
        **record.get("inputs", {}),
        "provenance_note": record.get("dataset", {}).get("provenance_note", ""),
    }


def feature_search(payload: dict) -> dict:
    """Bounded validation-only ridge feature subset search; final test never ranks trials."""
    from .ml import FEATURE_NAMES, run_ml

    bars, _ = fixtures()
    if payload.get("market_csv"):
        bars = load_bars(payload["market_csv"], content=True)
    if len(bars) > 2000:
        raise ValueError("Exploratory search is limited to 2,000 bars")
    trials = int(payload.get("trials", 5))
    if not 1 <= trials <= 10:
        raise ValueError("Search budget must be 1..10 trials")
    rng = random.Random(int(payload.get("seed", 42)))
    features = list(FEATURE_NAMES)
    rows = []
    for _ in range(trials):
        subset = sorted(rng.sample(features, rng.randint(1, len(features))))
        run = run_ml(bars, {"feature_names": subset, "ridge_alphas": [1.0]})
        rows.append(
            {
                "features": subset,
                "validation": run["validation"],
                "selected_alpha": run["model"].get("alpha"),
            }
        )
    return {
        "trial_count": trials,
        "seed": int(payload.get("seed", 42)),
        "trials": rows,
        "warning": "Exploratory validation results only. Multiple testing can overfit validation; hold out fresh data before drawing conclusions. No test scores are shown or used to rank trials.",
    }


def events_csv(events: list[dict]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(
        output, fieldnames=["observed_at", "available_at", "value", "field", "location"]
    )
    writer.writeheader()
    writer.writerows(events)
    return output.getvalue()
