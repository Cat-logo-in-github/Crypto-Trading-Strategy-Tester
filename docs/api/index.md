# Public Python and local HTTP APIs

The v0.3 interfaces are small pre-1.0 extension boundaries. Inputs and research records are JSON-compatible; arbitrary browser-submitted Python, pickle and joblib objects are not executed. The core has no runtime dependencies beyond Python's standard library.

## Guided studio additions

`POST /api/algorithm/plan` takes `{description,fields}` and optional user `connection`/session `credential`. It returns a reviewed draft `{entry,exit,signals,sizing,amount,weight}`, executable/clarification flags, available functions and data search terms. It does not assert that the requested data exists. `POST /api/algorithm/preview` accepts the normal data/execution payload plus that algorithm and returns a bounded sample/interpretation/period/warnings without retaining an experiment. `POST /api/run` supports `mode:"algorithm"` alongside rules/ml/model/endpoint.

`algorithm.signals` is a list of distinct `{name,expression}` definitions evaluated causally in order. `algorithms.SignalInterpreter`, `apply_signals` and `algorithm_decisions` expose the same bounded operations in Python. See [Signal Studio](../signal-studio.md) for math, text-derived/geographic conditions and limits. There is no unrestricted Python execution.

`period:{start,end,last_bars}` selects the historical research window. UTC date-only end values include that day; only completed market bars ending by the limit are selected. Rules/algorithms retain prior warmup but trade only inside the active window. Models use chronological held-out evaluation within the selected period. Records distinguish `period` from the actual portfolio `evaluation` window. `backtest`, `benchmark` and `decisions_for` accept keyword `start_index` inclusive / `end_index` exclusive bounds.

`GET /api/execution/profiles` returns dated profile metadata, official fee evidence, source links and separate assumptions. Execution configuration adds `fixed_fee` (quote currency/fill), `spread_bps` (full spread), `data_delay_ms` and `latency_ms`. `Decision.available_at` optionally declares later readiness. `model_config.include_inference_latency` defaults true for endpoint replay, using measured current service duration as a scenario. Costs and clocks are detailed in the [engine audit](../engine-audit-2026.md).

`inspect_dataset` now also returns `quality`, `interpretation` and `suggestions`. Formats include CSV/TSV/JSON/NDJSON/GeoJSON Point/properties. Composite calendar parts, explicit date layouts, typed entity filters, text equality and causal day/month event aggregation are supported; see [data mapping contracts](../data-sources.md). `align_features` accepts `decision_delay_seconds=0.0`. Catalog search adds auto/nasa/europa/hdx with relevance and supported-table/reference distinctions. Static studio/icon assets are bundled with the local app and Pages.

## Data, rules and execution

```python
from hypothesis_lab.data import Bar, Event, fixtures, load_bars, load_events
from hypothesis_lab.engine import Decision, ExecutionConfig, backtest, benchmark
from hypothesis_lab.strategies import decisions_for, python_decisions

bars, events = fixtures()
config = ExecutionConfig(initial_cash=10_000, fee_bps=10,
                         slippage_bps=5, periods_per_year=365,
                         bar_seconds=86400)
intents = [Decision(target_weight=1)] + [None] * (len(bars) - 1)
result = backtest(bars, intents, config)
baseline = benchmark(bars, config)
```

`Bar(timestamp, open, high, low, close, volume=0)` and `Event(observed_at, available_at, value, field=..., location=...)` are immutable validated records. Bar timestamps are UTC-normalized interval opens. Strictly increasing bars, finite positive OHLC and explicit duration are required. `load_bars`/`load_events` accept local paths or CSV text with `content=True`.

`Decision` accepts exactly one of `target_weight` or fee-inclusive `buy_cash`. `None` holds without a new order. One intent slot exists per completed bar; the engine fills at the first later supplied open at or after data, decision and submission readiness, and expires an intent with no eligible supplied open. Results contain metrics, equity/portfolio snapshots, fills, orders, execution config and warnings. Fills include costs and portfolio changes; these records are evidence, not an interface for creating fictional executions.

Rule trees use `all`/`any` groups and named comparisons. Mapped external fields use `event:field_name`; market features such as `close`, `sma_20` and `momentum_20` use their supported names. `parse_hypothesis(text, fields=None)` recognizes documented full-match grammars and can resolve mapped field aliases. It rejects unsupported prose. A trusted local Python strategy implements `decide(history: tuple[Bar, ...]) -> Decision | None`; `python_decisions` supplies the immutable history prefix through that completed bar.

## Domain-independent feature boundary

```python
from hypothesis_lab.features import (
    inspect_dataset, prepare_dataset, align_features, derive_features,
)

mapping = {
    "observed_at_column": "observed_at",
    "available_at_column": "available_at",
    "availability_mode": "column",
    "field_columns": ["merch_sales", "traffic_count"],
    "categorical_columns": [],
    "max_age_hours": 48,
}
info = inspect_dataset(csv_text, "csv", mapping)
observations, info = prepare_dataset(csv_text, "csv", mapping)
rows = align_features(bars, observations, info, config.bar_seconds)
rows = derive_features(rows, [{"source": "merch_sales", "name": "merch_growth_7",
                              "operation": "pct_change", "window": 7}])
```

The example assumes the caller supplies `csv_text`. Supported formats are CSV and JSON records. Inputs are bounded to 4 MB, 20,000 observations and 100 flattened columns. Mapping selects numeric fields, optional categorical fields, optional explicit text features and timestamp policy. Encoded model inputs are capped at 32. Missing data remains missing; availability, revisions and expiry are resolved before inference. Causal transformations are named lag/difference/proportional-change/mean/sum/z-score operations, not executable expressions.

The normalized `info.mapping` records acquisition time when used, explicit timezone/lag assumptions and expiry. `as_events(observations)` provides rule-compatible events. `research.run_experiment` applies the chosen generic expiry to its rule and model paths. Direct low-level callers must preserve the same intended clock and expiry conventions themselves.

## Basic and user-supplied models

`models.run_tabular_model(bars, feature_rows, config, pretrained=None)` accepts one named-feature row per market bar. The core trains CPU logistic probabilities or ridge numeric predictions. Configure feature names, a target field, `increase`/`return`/`level`, horizon and chronological split fractions. Boundary labels are purged and scaling uses training only; validation selects supported regularization settings. See [model inputs](../model-inputs.md) for full model schemas.

An explicit decision policy separates inference from execution:

```json
{
  "comparison": ">",
  "threshold": 0.5,
  "when_true": {"buy_cash": 100},
  "when_false": "hold"
}
```

`models.inspect_uploaded(artifact)` validates/reports supported model inputs and outputs. `models.infer_uploaded(artifact, rows, config=None)` performs numeric JSON or optional ONNX inference. JSON artifacts support validated logistic/ridge/linear numerical parameters; input remapping is explicit. ONNX is an optional CPU runtime route with a documented numeric matrix input/output contract. Native ONNX execution was not verified in this environment; inspect the status report rather than assuming an installed runtime or model exists.

Small ONNX uploads use `format:"onnx"` and `data_base64`; local paths use an existing absolute `model_path` plus `allow_local_file:true`. Large local files/weights remain outside the release. Feature order, output name/column, output meaning and user-declared training provenance are explicit settings. Unsupported frameworks and multimodal inputs can use user preprocessing or a compatible service, not hidden conversion.

`local_inference.run_endpoint_model(bars, feature_rows, config, connection, credential=None)` performs bounded user-endpoint replay through the shared engine. `call_llm` and `llm_plan` support an optional user-operated OpenAI-compatible service. Signals can be a strict JSON numeric field, defined text signal or provider-reported token count. Localhost is the default; remote HTTPS needs `allow_remote:true`. Endpoint outputs are compared with configured future target labels where available, while modern pretraining/future-knowledge and latency limitations remain explicit.

## Providers and orchestration

`sources.catalog()` describes implemented connectors and references. `search_sources(query, catalog_name="socrata", limit=12)` returns candidate metadata from supported public catalogs. `fetch_source(config, credential=None)` supports Socrata, World Bank, PortWatch and a bounded custom public HTTPS CSV/JSON source. It returns content, format, provenance, warnings and mapping suggestions. The credential is separate and is not included in exported metadata. See [data sources](../data-sources.md) for exact connector configs.

`ideas.plan_idea(query, fields=None)` proposes inspectable measurements, search terms, candidate signals and clarifications; it does not execute a generated strategy or assert that a matching source exists.

`research.run_experiment(payload, persist=False)` is the recommended explicit non-persistent Python call. Choose `mode` from `rules`, `ml`, `model` or `endpoint`; supply market/event CSV, generic feature data/mapping, transformations and the relevant strategy/model/connection settings. Set `persist=True` deliberately when calling this helper if a local saved record is wanted. The browser route separately defaults to session-only unless `persist_local:true` is supplied. The original `ml.run_ml` five-market-feature ridge baseline and the bounded experimental RL API remain available.

A result includes `market`, `ledger`, strategy/benchmark results, configuration, input identity, warnings and `diagnostics.inference_decisions`. Model rows link input values, output, target outcome, requested intent and actual fill/no-change status. Following-bar return is not whole-trade realized P&L. `rerun_payload(record)` reconstructs the input configuration; external files/services or a newly supplied session credential may still be required.

## Local HTTP routes

This is a localhost single-user API, not a public hosted service. Read `/api/bootstrap` for the current token and capabilities. Mutating requests require JSON, the loopback Host, matching local Origin and `X-Lab-Token`; do not disable these checks. The UI handles this session protocol.

| Route | Purpose and principal inputs |
| --- | --- |
| `GET /api/bootstrap` | Version, token, supported preset/demo/examples, credential status and optional model capabilities |
| `POST /api/ideas/plan` | `query`, optional mapped `fields`; optional selected `connection` and session `credential` for LLM planning |
| `POST /api/dataset/inspect` | `content`, `format`, optional `mapping`; returns preview, types, generated fields and normalized timestamp policy |
| `GET /api/sources/catalog` | Connector descriptions and access boundaries |
| `POST /api/sources/search` | `query`, `catalog` (`socrata` or `worldbank`) |
| `POST /api/sources/fetch` | Connector `config` and optional separate session `credential` |
| `POST /api/model/inspect` | Supported numeric JSON or optional ONNX `artifact`; no model persistence |
| `POST /api/connections/test` | Optional LLM `connection` and separate `credential`; an explicit provider request |
| `POST /api/parse` / `POST /api/preset` | Supported sentence with optional mapped `fields`, or preset settings |
| `POST /api/run` | Structured experiment payload; `persist_local` is false unless explicitly true |
| `GET /api/history` | Session summaries; `?include_saved=1` deliberately includes saved local runs |
| `GET /api/experiments/{id}` | Token-protected full session/saved research record |
| `POST /api/import` / `POST /api/rerun` | Imported record or stored `id`; explicit local saving and required session model key remain separate choices |
| `POST /api/search` | Legacy bounded market-feature subset experiment, separate from catalog search |
| `POST /api/settings/save`, `/remove`, `/test` | Separately consented legacy Alpha Vantage local-key workflow |
| `POST /api/feed` / `POST /api/weather` | Optional original read-only market/weather connectors |
| `POST /api/shutdown` | Stop the local service |

Run/import/model-inspection/dataset-inspection envelopes accept up to 12 MB of JSON so encoding overhead does not reject a valid smaller artifact. Other request envelopes use 3 MB; individual parser/model/provider limits still apply. Heavy model weights, dependency environments and SDKs are not release artifacts: the source packager enforces 20 MB ZIP and 10 MB per-source-file budgets.

A custom provider must return truthful availability/provenance and validated observations. A custom metric consumes completed equity/fills/config and documents undefined cases; it does not alter execution. Automatic plugin discovery and unrestricted code/model execution in the UI are not implemented extension mechanisms.
