"""Research orchestration, explicit dataset provenance and comparison."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import random
from dataclasses import asdict
from datetime import timedelta
from typing import Any, cast

from .algorithms import algorithm_decisions, apply_signals, signal_rows
from .data import fingerprint, fixtures, load_bars, load_events
from .engine import Decision, ExecutionConfig, backtest, benchmark
from .features import align_features, as_events, demo_content, derive_features, prepare_dataset
from .local_inference import public_connection
from .periods import select_period
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
    cfg_data = payload.get("execution", {})
    allowed = set(ExecutionConfig.__dataclass_fields__)
    if not isinstance(cfg_data, dict) or set(cfg_data) - allowed:
        raise ValueError("Unknown execution setting")
    if any(isinstance(value, bool) for value in cfg_data.values()):
        raise ValueError("Execution settings must be numbers, not booleans")
    cfg = ExecutionConfig(
        **{k: float(v) for k, v in {**asdict(ExecutionConfig()), **cfg_data}.items()}
    )
    profile = None
    if payload.get("execution_profile"):
        from .costs import execution_profiles

        profile = next(
            (item for item in execution_profiles() if item["id"] == payload["execution_profile"]),
            None,
        )
        if profile is None:
            raise ValueError("Choose a known cost profile, or clear it for custom assumptions")
    bars, active_start, period = select_period(bars, payload.get("period"), cfg.bar_seconds)
    feature_data = payload.get("feature_data", "")
    feature_format = payload.get("feature_format", "csv")
    feature_info = None
    feature_mapping = payload.get("feature_mapping", {})
    transforms = payload.get("transforms", [])
    if (
        payload.get("mode") in {"model", "endpoint"}
        and not feature_data
        and not payload.get("market_csv")
    ):
        feature_data = demo_content()
    if feature_data:
        observations, feature_info = prepare_dataset(feature_data, feature_format, feature_mapping)
        feature_mapping = feature_info["mapping"]
        aligned = derive_features(
            align_features(
                bars,
                observations,
                feature_info,
                cfg.bar_seconds,
                decision_delay_seconds=getattr(cfg, "data_delay_ms", 0) / 1000,
            ),
            transforms,
        )
        events = (
            load_events(payload["events_csv"], content=True) if payload.get("events_csv") else []
        ) + as_events(observations)
        # Derived features become available only at the decision close that computed them.
        if transforms:
            from .data import Event

            for i, row in enumerate(aligned):
                when = bars[i].timestamp + timedelta(
                    seconds=cfg.bar_seconds + cfg.data_delay_ms / 1000
                )
                for transform in transforms:
                    name = transform["name"]
                    value = row.get(name)
                    if value is not None:
                        events.append(Event(when, when, value, name, "Feature table"))
    mode = payload.get("mode", "rules")
    if not feature_data:
        aligned = [{} for _ in bars]
        if mode in {"model", "endpoint"}:
            feature_info = {
                "format": "market",
                "columns": ["market.close", "market.volume", "market.return_1"],
                "generated_fields": ["market.close", "market.volume", "market.return_1"],
                "mapping": {"max_age_hours": 48},
                "rows": len(bars),
                "warnings": [
                    "Only the supplied market measurements are used; no unrelated synthetic external data was added."
                ],
            }
    algorithm = payload.get("algorithm", {})
    if not isinstance(algorithm, dict):
        raise ValueError("Algorithm configuration must be an object")
    aligned = apply_signals(
        signal_rows(bars, aligned, cfg.bar_seconds, cfg.data_delay_ms / 1000),
        algorithm.get("signals", []),
    )
    spec = dict(payload.get("strategy") or preset("weather", slow=200))
    if feature_info:
        # One visible expiry policy applies to both rule and model workflows.
        spec["event_max_age_hours"] = feature_info["mapping"]["max_age_hours"]
    spec["data_delay_ms"] = getattr(cfg, "data_delay_ms", 0)
    if mode in {"model", "endpoint"}:
        assert feature_info is not None
        config = {**payload.get("model_config", {}), **asdict(cfg)}
        if "period" in payload and payload.get("pretrained"):
            config.setdefault("evaluation_start_index", 0)
        if "period" in payload and mode == "endpoint":
            config.setdefault("evaluation_start_index", 0)
        if not config.get("feature_names"):
            config["feature_names"] = feature_info["generated_fields"][:5]
        pretrained = payload.get("pretrained")
        if pretrained and pretrained.get("feature_mapping"):
            config["feature_mapping"] = pretrained["feature_mapping"]
        if mode == "endpoint":
            from .local_inference import run_endpoint_model

            result = run_endpoint_model(
                bars[active_start:],
                aligned[active_start:],
                config,
                payload.get("connection", {}),
                payload.get("model_credential"),
            )
        else:
            from .models import run_tabular_model

            result = run_tabular_model(
                bars[active_start:], aligned[active_start:], config, pretrained
            )
        strategy, base = result["backtest"], result["benchmark"]
    elif mode == "ml":
        from .ml import run_ml

        ml_config = {**payload.get("ml", {}), **asdict(cfg)}
        result = run_ml(bars[active_start:], ml_config)
        strategy, base = result["backtest"], result["benchmark"]
    elif mode == "rules":
        if float(spec.get("bar_seconds", cfg.bar_seconds)) != cfg.bar_seconds:
            raise ValueError("Strategy and execution bar duration must agree")
        result = {}
        runtime_spec = (
            {**spec, "_aligned_features": aligned}
            if feature_info or algorithm.get("signals")
            else spec
        )
        strategy = backtest(
            bars,
            decisions_for(bars, runtime_spec, events, start_index=active_start),
            cfg,
            start_index=active_start,
        )
        base = benchmark(bars, cfg, start_index=active_start)
    elif mode == "algorithm":
        decisions, interpretation = algorithm_decisions(aligned, algorithm)
        entry_values = interpretation.pop("entry_values")
        exit_values = interpretation.pop("exit_values")
        interpretation.update(
            entry_matches=sum(bool(v) for v in entry_values[active_start:]),
            exit_matches=sum(bool(v) for v in exit_values[active_start:]),
            missing_entry_rows=sum(v is None for v in entry_values[active_start:]),
        )
        strategy = backtest(bars, decisions, cfg, start_index=active_start)
        base = benchmark(bars, cfg, start_index=active_start)
        orders = {item["submitted_bar"]: item for item in strategy["orders"]}
        previews = []
        for index in range(active_start, len(bars)):
            previews.append(
                {
                    "timestamp": bars[index].timestamp.isoformat(),
                    "decision_at": (
                        bars[index].timestamp
                        + timedelta(
                            seconds=cfg.bar_seconds + getattr(cfg, "data_delay_ms", 0) / 1000
                        )
                    ).isoformat(),
                    "index": index - active_start,
                    "bar_index": index - active_start,
                    "prediction": entry_values[index],
                    "actual": None,
                    "exit_output": exit_values[index],
                    "condition_matched": bool(entry_values[index]),
                    "decision": "cash"
                    if exit_values[index]
                    else "long"
                    if entry_values[index]
                    else "hold",
                    "features": aligned[index],
                    "intent": asdict(cast(Decision, decisions[index]))
                    if decisions[index]
                    else None,
                    "execution_status": orders.get(index, {}).get("status", "hold"),
                    "fills": [
                        fill
                        for fill in strategy["fills"]
                        if fill["decision_bar_open"] == bars[index].timestamp.isoformat()
                    ],
                }
            )
        result = {"interpretation": interpretation, "inference_decisions": previews}
    else:
        raise ValueError("Supported modes are rules, algorithm, ml, model and endpoint")
    # All model/rule paths share the same optional execution backend. Training is
    # completed once; replacing execution must never reselect on the test P&L.
    replay = payload.get("execution_replay")
    portfolio = payload.get("portfolio")
    if replay and portfolio:
        raise ValueError(
            "Choose single-instrument event replay or linked-contract portfolio execution"
        )
    if replay or portfolio:
        evaluation_start = next(
            i
            for i, bar in enumerate(bars)
            if bar.timestamp.isoformat() == strategy["equity"][0]["timestamp"]
        )
        executed_decisions: list[Any]
        if mode == "rules":
            executed_decisions = decisions_for(
                bars, runtime_spec, events, start_index=evaluation_start
            )
        elif mode == "algorithm":
            executed_decisions = decisions
        else:
            executed_decisions = [None] * len(bars)
            by_time = {bar.timestamp.isoformat(): i for i, bar in enumerate(bars)}
            for prediction in result.get("inference_decisions", result.get("predictions", [])):
                index = by_time[prediction["timestamp"]]
                if "intent" in prediction:
                    executed_decisions[index] = (
                        Decision(**prediction["intent"]) if prediction["intent"] else None
                    )
                elif prediction["decision"] != "hold":
                    executed_decisions[index] = Decision(
                        target_weight=1.0 if prediction["decision"] == "long" else 0.0
                    )
        if portfolio:
            from .algorithms import SignalInterpreter
            from .portfolio import portfolio_backtest

            if (
                not isinstance(portfolio, dict)
                or not isinstance(portfolio.get("legs"), dict)
                or not portfolio["legs"]
            ):
                raise ValueError(
                    "Linked-contract execution needs a signed quantity or causal expression for each leg"
                )
            quantities = {
                symbol: SignalInterpreter(aligned).run(value)
                if isinstance(value, str)
                else [value] * len(bars)
                for symbol, value in portfolio["legs"].items()
            }
            targets: list[dict | None] = []
            for index, intent in enumerate(executed_decisions):
                if intent is None or any(values[index] is None for values in quantities.values()):
                    targets.append(None)
                    continue
                if intent.buy_cash is not None:
                    raise ValueError(
                        "Linked contracts require target exposure and explicit signed leg quantities; a single cash-buy budget cannot size a derivatives basket"
                    )
                else:
                    scale = intent.target_weight or 0.0
                targets.append(
                    {
                        "targets": {
                            symbol: float(cast(float, values[index])) * scale
                            for symbol, values in quantities.items()
                        },
                        "available_at": intent.available_at,
                    }
                )
            strategy = portfolio_backtest(
                bars, targets, cfg, portfolio, start_index=evaluation_start
            )
            base = portfolio_backtest(
                bars, [None] * len(bars), cfg, portfolio, start_index=evaluation_start
            )
            base["label"] = "Same-currency cash and declared cash interest; no linked positions"

        else:
            from .microstructure import ReplayConfig, replay_backtest, replay_benchmark

            if not isinstance(replay, dict):
                raise ValueError("Execution replay configuration must be an object")
            replay_config = {
                key: value
                for key, value in replay.items()
                if key in ReplayConfig.__dataclass_fields__
            }
            raw = replay.get("records", replay.get("content", []))
            if not isinstance(raw, (str, list)):
                raise ValueError("Replay needs event records or file text")
            form = replay.get("format", "records")
            raw_intents = payload.get("execution_intents")
            if raw_intents is not None:
                if not isinstance(raw_intents, list) or len(raw_intents) != len(bars):
                    raise ValueError(
                        "Provide one explicit replay intent slot per retained reference bar"
                    )
                executed_decisions = raw_intents
            strategy = replay_backtest(
                bars,
                cast(list[Decision | dict | None], executed_decisions),
                cfg,
                raw,
                replay_config,
                start_index=evaluation_start,
                format=form,
            )
            base = replay_benchmark(
                bars, cfg, raw, replay_config, start_index=evaluation_start, format=form
            )
        for prediction in result.get("inference_decisions", result.get("predictions", [])):
            prediction["fills"] = [
                fill
                for fill in strategy["fills"]
                if fill["decision_bar_open"] == prediction["timestamp"]
            ]
            prediction["execution_status"] = (
                "filled" if prediction["fills"] else "no_fill_in_replay"
            )
        if mode in {"model", "endpoint", "ml"}:
            result["backtest"] = strategy
            result["benchmark"] = base
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
                    + json.dumps(
                        {"start": period["start"], "end": period["end"], "bars": period["bars"]},
                        sort_keys=True,
                    )
                    + json.dumps(algorithm.get("signals", []), sort_keys=True)
                    + hashlib.sha256(
                        json.dumps(
                            {"portfolio": portfolio, "execution_replay": replay}, sort_keys=True
                        ).encode()
                    ).hexdigest()
                ).encode()
            ).hexdigest(),
            "source": source,
            "rows": len(bars) - active_start,
            "warmup_rows": active_start,
            "start": bars[active_start].timestamp.isoformat(),
            "end": bars[-1].timestamp.isoformat(),
            "location": spec.get("location"),
            "provenance_note": str(payload.get("provenance_note", ""))[:1000],
        },
        "configuration": {
            "strategy": spec,
            "execution": asdict(cfg),
            "execution_profile": profile,
            "ml": payload.get("ml", {}),
            "feature_mapping": feature_mapping,
            "model_config": result.get("configuration", payload.get("model_config", {})),
            "transforms": transforms,
            "algorithm": algorithm,
            "period": period["requested"],
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
            "portfolio": portfolio,
            "execution_replay": replay,
            "execution_intents": payload.get("execution_intents"),
        },
        "strategy": strategy,
        "benchmark": base,
        "ml": result if mode == "ml" else None,
        "model": result if mode in {"model", "endpoint"} else None,
        "market": [
            {**asdict(bar), "timestamp": bar.timestamp.isoformat()} for bar in bars[active_start:]
        ],
        "period": period,
        "evaluation": {
            "start": strategy["equity"][0]["timestamp"],
            "end": strategy["equity"][-1]["valuation_at"],
            "bars": len(strategy["equity"]),
            "note": "This is the actual portfolio/benchmark evaluation window. The research input period can also contain earlier model-training and indicator-warmup observations.",
        },
        "algorithm": result.get("interpretation") if mode == "algorithm" else None,
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
    from .validation import uncertainty

    record["evidence"] = uncertainty(strategy, base)
    record["portfolio"] = strategy.get("portfolio")
    record["execution_replay"] = strategy.get("replay")
    if portfolio and portfolio.get("data_status"):
        record["warnings"].append(portfolio["data_status"])
    if not payload.get("market_csv"):
        record["warnings"].append(
            "Synthetic fixtures are for software demonstration only; results are not market performance."
        )
    if mode in {"ml", "model", "endpoint"}:
        record["warnings"].extend(result.get("warnings", []))
    if payload.get("period") and mode in {"ml", "model"} and not payload.get("pretrained"):
        record["warnings"].append(
            "The selected research period contains chronological training, validation and held-out test windows. Trading performance is evaluated only in the held-out subperiod shown in the model diagnostics."
        )
    if mode == "algorithm":
        record["warnings"].append(
            "Custom signal expressions use trailing measured inputs only; geographic boxes and text matches are user-defined measurements, not automatic verification of a real-world event. Invalid arithmetic and missing warmup produce missing signals."
        )
    if feature_info:
        record["warnings"].extend(feature_info["warnings"])
        record["dataset"]["feature_fields"] = feature_info["generated_fields"]
    if profile:
        record["warnings"].append(
            "The selected venue profile is a dated schedule snapshot with separate illustrative spread/slippage/delay assumptions. Your numeric execution settings, including edits, are authoritative; current rates are not a historical fee archive."
        )
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
        "execution_profile": (config.get("execution_profile") or {}).get("id"),
        "ml": config.get("ml", {}),
        "feature_mapping": config.get("feature_mapping", {}),
        "model_config": config.get("model_config", {}),
        "transforms": config.get("transforms", []),
        "algorithm": config.get("algorithm", {}),
        "period": config.get("period", {}),
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
