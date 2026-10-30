"""Five fixed, deliberately unusual software trials; never evidence of a market edge.

The observation and market generators use independent RNG streams. Definitions,
seeds, thresholds and controls are fixed before evaluation, not chosen by returns.
No network, persistence, heavy dependencies, LLM responses or executable models.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
import random
from datetime import UTC, datetime, timedelta
from typing import Any

from .algorithms import apply_signals, plan_algorithm, signal_rows
from .data import load_bars
from .features import align_features, prepare_dataset
from .research import rerun_payload, run_experiment

START = datetime(2022, 1, 1, tzinfo=UTC)
DAYS = 420
SEED = 20261029
VERSION = "scenario-lab/v1"
IDS = ("horror_library", "repair_cafe", "pigeon_pizza", "gnome_auction", "speedrunner_knitting")
BOX = (51.04, -114.08, 51.06, -114.05)  # An illustrative rectangle, not a venue claim.

_DESCRIPTORS: tuple[dict[str, Any], ...] = (
    {
        "id": IDS[0],
        "title": "The midnight horror shelf",
        "format": "csv",
        "mode": "algorithm",
        "question": "Buy $100 when horror_share > 0.35 and horror_change_20 > 0; sell when horror_share < 0.30.",
        "story": "Could a rise in horror borrowing at one library branch coincide with risk appetite?",
        "measurements": [
            "Monthly horror loans and all loans, branch identity, year/month and actual publication time"
        ],
        "structure": "Monthly panel CSV; explicit North-branch filter; separate year/month calendar columns.",
        "target": "A fixed observed-share condition; no predictive model",
        "traded_asset": "Synthetic risk-asset spot price",
        "seed": SEED + 11,
        "limits": [
            "Only fourteen months; not independent daily evidence.",
            "Library data is not a verified sentiment measure.",
        ],
    },
    {
        "id": IDS[1],
        "title": "The burnt-toaster repair queue",
        "format": "ndjson",
        "mode": "model",
        "question": "Predict whether the repair-cafe waiting queue will increase three market bars ahead; buy $100 if that probability is above 0.55, otherwise hold.",
        "story": "Does today's repair mix forecast a future community repair queue, and does trading on that forecast do anything useful?",
        "measurements": [
            "Daily completed/failed repairs, waiting queue, timestamped repair notes and publication time"
        ],
        "structure": "Nested NDJSON records; explicit burnt-phrase count; chronological logistic training.",
        "target": "queue.waiting increases over three bars",
        "traded_asset": "Synthetic risk-asset spot price",
        "seed": SEED + 23,
        "limits": [
            "Forecasting a repair queue is different from forecasting a traded instrument.",
            "Text counts do not establish cause or sentiment.",
        ],
    },
    {
        "id": IDS[2],
        "title": "Pigeons at the pizza-box plaza",
        "format": "geojson",
        "mode": "algorithm",
        "question": "Buy $100 when plaza_sightings_7 > 3; sell when plaza_sightings_7 < 2.",
        "story": "Could a seven-day average of pigeon-and-pizza sightings in one explicit rectangle be a trading signal?",
        "measurements": [
            "Point coordinates, timestamped sightings, complete daily reporting and publication time"
        ],
        "structure": "GeoJSON Points; explicitly calculated inside_plaza property; region filter then daily event counts.",
        "target": "Seven-bar average daily sighting count",
        "traded_asset": "Synthetic risk-asset spot price",
        "seed": SEED + 37,
        "limits": [
            "The rectangle is illustrative, not a claim about a real plaza.",
            "Events missing from a real feed would not imply zero sightings.",
            "No polygon centroids or satellite events are invented.",
        ],
    },
    {
        "id": IDS[3],
        "title": "Garden-gnome auction confidence",
        "format": "json",
        "mode": "model",
        "question": "Use the uploaded gnome-auction model to predict clearance; buy $100 when probability > 0.55, otherwise exit.",
        "story": "Replay a small transparent numeric artifact on listing text and bids, with an external auction-clearance target.",
        "measurements": [
            "Listing descriptions, bid count, clearance rate and their historical availability"
        ],
        "structure": "JSON records wrapper; authentic/damage phrase counts; JSON-serialized numeric logistic upload.",
        "target": "auction.clearance increases next bar",
        "traded_asset": "Synthetic risk-asset spot price",
        "seed": SEED + 41,
        "limits": [
            "Artifact weights are hand-authored for adapter testing, not a trained financial model.",
            "No pickle, framework weights or model downloads are used.",
        ],
    },
    {
        "id": IDS[4],
        "title": "Speedrunner resets and knitting fever",
        "format": "tsv",
        "mode": "model",
        "question": "Use speedrunner resets and personal-best attempts to predict whether knitting_searches will exceed its seven-bar average three bars ahead; target 60% long exposure when probability > 0.55, otherwise exit.",
        "story": "Can stream-reset telemetry predict an explicitly defined future knitting-search condition, and is that separate forecast useful to a paper portfolio?",
        "measurements": [
            "Completed daily reset and personal-best counts, knitting-search index, publication time"
        ],
        "structure": "TSV telemetry; custom future Boolean target; chronological logistic baseline.",
        "target": "knitting_searches above its trailing seven-bar mean at t+3",
        "traded_asset": "Synthetic risk-asset spot price",
        "seed": SEED + 59,
        "limits": [
            "Targets use a later available measurement; features remain causal.",
            "A search index is neither purchases nor a claim about population behavior.",
        ],
    },
)


def catalogue() -> list[dict[str, Any]]:
    """Return fresh metadata; callers cannot mutate the fixed trial definitions."""
    return [
        {
            **copy.deepcopy(item),
            "version": VERSION,
            "default_days": DAYS,
            "data_status": "Entirely synthetic controlled software trial",
            "methodology": "Fixed definitions and independent RNG streams; no return-based selection.",
        }
        for item in _DESCRIPTORS
    ]


def _table(rows: list[dict], delimiter: str = ",") -> str:
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=list(rows[0]), delimiter=delimiter, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def _market(days: int) -> str:
    rng = random.Random(SEED + 100003)
    rows, previous = [], 100.0
    for index in range(days):
        opened = previous * math.exp(rng.gauss(0, 0.003))
        closed = opened * math.exp(rng.gauss(0.00015, 0.012))
        rows.append(
            {
                "timestamp": (START + timedelta(days=index)).isoformat(),
                "open": opened,
                "high": max(opened, closed) * (1 + rng.uniform(0.001, 0.009)),
                "low": min(opened, closed) * (1 - rng.uniform(0.001, 0.009)),
                "close": closed,
                "volume": rng.randint(1000, 10000),
            }
        )
        previous = closed
    return _table(rows)


def _mapping(fields: list[str], **extra: Any) -> dict:
    return {
        "observed_at_column": "observed_at",
        "available_at_column": "available_at",
        "availability_mode": "column",
        "field_columns": fields,
        "categorical_columns": [],
        "max_age_hours": 72,
        "acquired_at": "2026-10-29T00:00:00+00:00",
        **extra,
    }


def _library(days: int, rng: random.Random) -> tuple[str, dict]:
    rows, cursor, month = [], START, 0
    while cursor < START + timedelta(days=days):
        next_month = datetime(
            cursor.year + (cursor.month == 12),
            1 if cursor.month == 12 else cursor.month + 1,
            1,
            tzinfo=UTC,
        )
        for branch in ("North", "South"):
            total = rng.randint(900, 1400)
            share = (
                0.34
                + 0.12 * math.sin(month * 1.1 + (branch == "South"))
                + rng.uniform(-0.025, 0.025)
            )
            rows.append(
                {
                    "Year": cursor.year,
                    "Month": cursor.month,
                    "branch": branch,
                    "horror_loans": round(total * share),
                    "all_loans": total,
                    "available_at": (next_month + timedelta(days=1, hours=8)).isoformat(),
                }
            )
        month += 1
        cursor = next_month
    return _table(rows), _mapping(
        ["horror_loans", "all_loans"],
        observed_at_column="",
        timestamp_parts={"year": "Year", "month": "Month"},
        timezone="UTC",
        period_boundary="end",
        entity_column="branch",
        filter={"column": "branch", "equals": "North"},
        max_age_hours=24 * 45,
    )


def _repair(days: int, rng: random.Random) -> tuple[str, dict]:
    rows = []
    for index in range(days):
        observed = START + timedelta(days=index, hours=16)
        waiting = max(1, round(18 + 7 * math.sin(index / 11) + rng.gauss(0, 2)))
        rows.append(
            {
                "observed_at": observed.isoformat(),
                "available_at": (observed + timedelta(hours=2)).isoformat(),
                "repair": {
                    "completed": rng.randint(2, 14),
                    "failed": rng.randint(0, 5),
                    "note": "burnt element, toaster" if index % 5 < 2 else "loose cable repaired",
                },
                "queue": {"waiting": waiting},
            }
        )
    return "\n".join(json.dumps(row, separators=(",", ":")) for row in rows), _mapping(
        ["repair.completed", "repair.failed", "queue.waiting"],
        text_features=[
            {
                "column": "repair.note",
                "name": "burnt_mentions",
                "operation": "count",
                "needle": "burnt",
            }
        ],
    )


def _pigeons(days: int, rng: random.Random) -> tuple[str, dict]:
    points = []
    south, west, north, east = BOX
    for index in range(days):
        # Complete synthetic reporting includes at least one in-region event daily.
        for event in range(1 + round(3 + 2 * math.sin(index / 13))):
            inside = event == 0 or rng.random() > 0.25
            lat, lon = (
                (rng.uniform(south, north), rng.uniform(west, east))
                if inside
                else (north + 0.01, east + 0.02)
            )
            observed = START + timedelta(days=index, hours=8 + event)
            points.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {
                        "observed_at": observed.isoformat(),
                        "available_at": (observed + timedelta(hours=1)).isoformat(),
                        "inside_plaza": south <= lat <= north and west <= lon <= east,
                        "label": "pigeon beside pizza box",
                    },
                }
            )
    return json.dumps(
        {"type": "FeatureCollection", "features": points}, separators=(",", ":")
    ), _mapping(
        [],
        filter={"column": "inside_plaza", "equals": True},
        entity_column="inside_plaza",
        aggregation={"frequency": "day", "operation": "count", "fields": []},
    )


def _gnomes(days: int, rng: random.Random) -> tuple[str, dict]:
    rows = []
    for index in range(days):
        observed = START + timedelta(days=index, hours=14)
        rows.append(
            {
                "observed_at": observed.isoformat(),
                "available_at": (observed + timedelta(hours=3)).isoformat(),
                "listing": {
                    "text": "authentic vintage gnome"
                    if index % 7 < 4
                    else "gnome with damage and repaired hat",
                    "bids": rng.randint(0, 12),
                },
                "auction": {
                    "clearance": round(
                        0.50 + 0.18 * math.sin(index / 8) + rng.uniform(-0.06, 0.06), 5
                    )
                },
            }
        )
    return json.dumps({"records": rows}, separators=(",", ":")), _mapping(
        ["listing.bids", "auction.clearance"],
        text_features=[
            {
                "column": "listing.text",
                "name": "authentic_count",
                "operation": "count",
                "needle": "authentic",
            },
            {
                "column": "listing.text",
                "name": "damage_count",
                "operation": "count",
                "needle": "damage",
            },
        ],
    )


def _speedrunner(days: int, rng: random.Random) -> tuple[str, dict]:
    rows = []
    for index in range(days):
        observed = START + timedelta(days=index, hours=20)
        rows.append(
            {
                "observed_at": observed.isoformat(),
                "available_at": (observed + timedelta(hours=2)).isoformat(),
                "reset_count": rng.randint(0, 25),
                "personal_best_attempts": rng.randint(0, 5),
                "knitting_searches": round(80 + 18 * math.sin(index / 10) + rng.gauss(0, 4), 4),
            }
        )
    return _table(rows, "\t"), _mapping(
        ["reset_count", "personal_best_attempts", "knitting_searches"]
    )


_BUILDERS = dict(zip(IDS, (_library, _repair, _pigeons, _gnomes, _speedrunner)))


def scenario_payload(
    identity: str,
    *,
    days: int = DAYS,
    market_csv: str | None = None,
    market_provenance: str | None = None,
) -> dict:
    """Build a normal run_experiment payload. User market data needs its own provenance.

    Synthetic observations are dated independently from the supplied market. Their
    coverage is never silently shifted to manufacture overlap with a real source.
    """
    if identity not in IDS:
        raise ValueError("Choose a scenario from the catalogue")
    if not isinstance(days, int) or isinstance(days, bool) or not 180 <= days <= 1500:
        raise ValueError("Choose 180 to 1,500 daily fixture rows")
    if market_csv is not None and not market_provenance:
        raise ValueError(
            "A user market CSV requires source, instrument, interval and usage provenance"
        )
    descriptor = next(item for item in _DESCRIPTORS if item["id"] == identity)
    content, mapping = _BUILDERS[identity](days, random.Random(descriptor["seed"]))
    body: dict[str, Any] = {
        "mode": descriptor["mode"],
        "name": descriptor["title"],
        "market_csv": market_csv if market_csv is not None else _market(days),
        "feature_data": content,
        "feature_format": descriptor["format"],
        "feature_mapping": mapping,
        "persist_local": False,
        "execution": {
            "initial_cash": 10000,
            "fee_bps": 10,
            "spread_bps": 8,
            "slippage_bps": 5,
            "fixed_fee": 0,
            "data_delay_ms": 0,
            "latency_ms": 0,
            "bar_seconds": 86400,
            "periods_per_year": 365,
        },
        "provenance_note": f"{VERSION}; fixed seed {descriptor['seed']}. All alternative observations are synthetic adapter/causality trials, never actual economic evidence. Market: {market_provenance if market_csv is not None else 'independently generated synthetic spot OHLCV; no real instrument performance'}.",
    }
    if identity == IDS[0]:
        signals = [
            {"name": "horror_share", "expression": "col('horror_loans') / col('all_loans')"},
            {"name": "horror_change_20", "expression": "difference(horror_share, 20)"},
        ]
        entry, leave = "horror_share > 0.35 and horror_change_20 > 0", "horror_share < 0.30"
    elif identity == IDS[2]:
        signals = [{"name": "plaza_sightings_7", "expression": "mean(col('event_count'), 7)"}]
        entry, leave = "plaza_sightings_7 > 3", "plaza_sightings_7 < 2"
    else:
        decision: dict[str, Any] = {
            "comparison": ">",
            "threshold": 0.55,
            "when_true": {"buy_cash": 100},
            "when_false": "hold" if identity == IDS[1] else "exit",
        }
        config: dict[str, Any] = {
            "horizon": 3 if identity != IDS[3] else 1,
            "target_type": "increase",
            "model_family": "logistic",
            "train_fraction": 0.6,
            "validation_fraction": 0.2,
            "epochs": 60,
            "l2_candidates": [0.01, 0.1],
            "decision": decision,
        }
        if identity == IDS[1]:
            config.update(
                feature_names=[
                    "repair.completed",
                    "repair.failed",
                    "queue.waiting",
                    "burnt_mentions",
                ],
                target_field="queue.waiting",
            )
        elif identity == IDS[3]:
            config.update(
                feature_names=["authentic_count", "damage_count", "listing.bids"],
                target_field="auction.clearance",
                evaluation_start_index=int(days * 0.8),
            )
            body["pretrained"] = {
                "format": "json",
                "model": {
                    "schema": "hypothesis-lab/tabular-v1",
                    "family": "logistic",
                    "feature_names": ["authentic", "damage", "bids"],
                    "means": [0, 0, 6],
                    "scales": [1, 1, 4],
                    "coefficients": [0.8, -0.9, 0.15],
                    "intercept": 0,
                },
                "feature_mapping": {
                    "authentic": "authentic_count",
                    "damage": "damage_count",
                    "bids": "listing.bids",
                },
            }
        else:
            config.update(
                feature_names=["reset_count", "personal_best_attempts", "knitting_searches"],
                target_field="knitting_searches",
                target_type="condition",
                target_condition="col('knitting_searches') > mean(col('knitting_searches'), 7)",
            )
            decision["when_true"] = {"target_weight": 0.6}
        body["model_config"] = config
        body["scenario_plan"] = {
            "compiled_automatically": False,
            "method": "Reviewed target, model, features and action configuration",
            "question": descriptor["question"],
        }
        return body
    plan = plan_algorithm(descriptor["question"], [item["name"] for item in signals])
    body["algorithm"] = {
        **(plan["draft"] if plan["executable"] else {"entry": entry, "exit": leave}),
        "signals": signals,
        "sizing": "cash",
        "amount": 100,
    }
    body["scenario_plan"] = {
        "compiled_automatically": plan["executable"],
        "method": "Deterministic plain-language planner"
        if plan["executable"]
        else "Reviewed explicit expressions; planner clarification retained",
        "question": descriptor["question"],
        "clarifications": plan["clarifications"],
    }
    # Fixed rules are evaluated only on the final 120 rows; prior history is warmup.
    body["period"] = {"last_bars": min(120, days // 2)}
    return body


def prefix_causality(payload: dict) -> dict:
    """Future publications and future bars must not alter earlier signal rows."""
    bars = load_bars(payload["market_csv"], content=True)
    observations, info = prepare_dataset(
        payload["feature_data"], payload["feature_format"], payload["feature_mapping"]
    )
    middle = len(bars) // 2
    cut = bars[middle - 1].timestamp + timedelta(days=1)
    signals = payload.get("algorithm", {}).get("signals", [])
    full = apply_signals(
        signal_rows(bars, align_features(bars, observations, info), 86400), signals
    )
    earlier = [item for item in observations if item.available_at <= cut]
    prefix = apply_signals(
        signal_rows(bars[:middle], align_features(bars[:middle], earlier, info), 86400), signals
    )
    return {
        "passed": full[:middle] == prefix,
        "compared_bars": middle,
        "publication_cutoff": cut.isoformat(),
        "future_publications_excluded": len(observations) - len(earlier),
    }


def _score(run: dict) -> dict:
    m, b = run["summary"], run["benchmark"]["metrics"]
    return {
        "run_id": run["id"],
        "total_return": m["total_return"],
        "benchmark_return": b["total_return"],
        "excess_return": m["excess_return"],
        "final_equity": m["final_equity"],
        "max_drawdown": m["max_drawdown"],
        "trade_count": m["trade_count"],
        "fees_paid": m["fees_paid"],
        "spread_cost": m.get("spread_cost"),
        "slippage_cost": m.get("slippage_cost"),
        "evaluation": run["evaluation"],
        "label": "Synthetic software-trial results; not evidence of effectiveness in real markets",
    }


def run_scenarios(
    identities: list[str] | None = None,
    *,
    include_controls: bool = True,
    include_records: bool = False,
    days: int = DAYS,
    market_csv: str | None = None,
    market_provenance: str | None = None,
) -> dict:
    """Execute the full ingestion → features → decisions/models → accounting pipeline.

    Records are not persisted. Controls are fixed sensitivity/implementation checks,
    not candidates from which the highest return is selected.
    """
    selected = list(IDS) if identities is None else list(identities)
    if (
        not selected
        or len(selected) != len(set(selected))
        or any(item not in IDS for item in selected)
    ):
        raise ValueError("Choose distinct scenario IDs from the catalogue")
    output = []
    for identity in selected:
        body = scenario_payload(
            identity, days=days, market_csv=market_csv, market_provenance=market_provenance
        )
        run = run_experiment(body, persist=False)
        replay = run_experiment(rerun_payload(run), persist=False)
        item = {
            "scenario": next(d for d in catalogue() if d["id"] == identity),
            "plan": body["scenario_plan"],
            "score": _score(run),
            "prefix_causality": prefix_causality(body),
            "replay_identical": replay["id"] == run["id"],
            "input_sha256": hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest(),
            "controls": [],
        }
        if include_records:
            item["run"] = run
        if include_controls:
            stress = copy.deepcopy(body)
            stress["execution"].update(fee_bps=30, spread_bps=40, slippage_bps=20, fixed_fee=1)
            item["controls"].append(
                {
                    "kind": "higher_costs",
                    "description": "Fixed adverse-cost scenario; not a venue quote or an optimized choice",
                    "score": _score(run_experiment(stress, persist=False)),
                }
            )
            threshold = copy.deepcopy(body)
            if body["mode"] == "algorithm":
                threshold["algorithm"]["entry"] = (
                    "horror_share > 0.40 and horror_change_20 > 0"
                    if identity == IDS[0]
                    else "plaza_sightings_7 > 4"
                )
            else:
                threshold["model_config"]["decision"]["threshold"] = 0.65
            item["controls"].append(
                {
                    "kind": "fixed_threshold_perturbation",
                    "description": "Predeclared nearby threshold; shown without selecting a winner",
                    "score": _score(run_experiment(threshold, persist=False)),
                }
            )
            delayed = copy.deepcopy(body)
            delayed["feature_mapping"].update(
                availability_mode="lag", availability_lag_hours=24 * (days + 730)
            )
            try:
                blank = run_experiment(delayed, persist=False)
            except ValueError as error:
                if "Need at least 12 train" not in str(
                    error
                ) and "No complete feature rows" not in str(error):
                    raise
                result = {
                    "passed": True,
                    "outcome": "No historically complete model inputs; evaluation correctly rejected",
                    "error": str(error),
                }
            else:
                result = {
                    "passed": not blank["strategy"]["fills"],
                    "outcome": "No publication was available during evaluation",
                    "score": _score(blank),
                }
            item["controls"].append({"kind": "unavailable_publication_negative_control", **result})
        output.append(item)
    return {
        "schema": VERSION,
        "data_status": "Synthetic controlled software trials"
        if market_csv is None
        else "Synthetic observations paired with user-supplied market prices; no real alternative-data claim",
        "methodology": "Fixed RNG seeds, independent market/observation streams, held-out model tests, fixed rules, matched buy-and-hold costs, replay/prefix checks and predeclared sensitivity controls. Nothing was optimized on reported test returns.",
        "scenarios": output,
        "audit_recommendations": [
            "Verify genuine point-in-time releases, units, entity coverage and source permission before using real data.",
            "Pre-register targets, horizons, thresholds, costs and the number of hypotheses tried; retain failed trials.",
            "Use multiple independent historical periods and instruments plus embargoed rolling validation; adjacent overlapping labels are not independent trials.",
            "Estimate net-return uncertainty with time-aware block resampling and an untouched forward period; no p-value or confidence interval is claimed here.",
            "Inspect missing-data coverage, revisions, clock alignment, fees, spread, latency and liquidity; daily bars do not reconstruct intrabar execution.",
            "External prediction accuracy, causal explanations and profitable trading are separate hypotheses.",
        ],
        "warnings": [
            "All alternative observations are labeled deterministic synthetic fixtures.",
            "Positive or negative numbers test the software pipeline, not an actual economic relationship.",
            "No model service or live source was called and no data was saved by this function.",
        ],
    }
