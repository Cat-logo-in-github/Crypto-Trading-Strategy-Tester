# Actual system architecture

The supported v0.3 package is `src/hypothesis_lab`, a student project for historical strategy research and simulated paper trading. A standard-library Python service binds to `127.0.0.1` and serves the guided studio and dark market terminal. There is no Node build step, mandatory cloud service, account, telemetry or paid core dependency. GitHub Pages serves the static landing page and documentation, not research execution.

## Shared research flow

```text
Question -> reviewable data requirements and candidate-source search
  -> local CSV/JSON, selected HTTPS provider or synthetic fixture
  -> immutable UTC market bars and availability-aware observations
  -> chosen numeric/categorical/text inputs and causal transformations
  -> rule intent, trained baseline or user-model inference
  -> explicit output-to-trade policy
  -> next-open execution, costs, cash and position accounting
  -> compatible benchmark, metrics, ledger and discrepancy inspection
  -> session record, optional local save and explicit export
```

The question planner proposes definitions rather than asserting that a dataset exists. Source discovery and measurement validation remain separate from strategy/model evaluation. A public catalog result is a candidate, not proof it measures the requested concept or carries unrestricted redistribution rights.

## Module boundaries

| Module | Actual responsibility |
| --- | --- |
| `data.py` | Immutable market `Bar` and external `Event` records, UTC/finite-value validation, market CSV loading and identity |
| `features.py` | CSV/TSV/JSON/NDJSON/GeoJSON tables, quality/suggested roles, composite dates, entity filters, causal aggregation, observation/publication mappings, expiry/revisions, text/categorical measurements and trailing transformations |
| `ideas.py` | Deterministic question-to-data-requirements proposal and clarifications |
| `sources.py` | Ranked public discovery across Socrata/World Bank/NASA/European/HDX catalogs, metadata versus table boundaries, bounded source fetches and custom HTTPS APIs; keys are arguments, not stored metadata |
| `algorithms.py` | Bounded causal expression interpreter, named signal chains, separate entry/exit intent and reviewed deterministic/user-model drafts; never Python eval |
| `periods.py` | UTC historical duration, completed-bar eligibility and earlier warmup selection |
| `costs.py` | Dated official commission evidence plus separately labeled editable spread/slippage/delay assumptions |
| `strategies.py` | Supported deterministic parsing, AND/OR rule trees, arbitrary `event:field` conditions and the trusted local Python strategy protocol |
| `ml.py` | Original five-market-feature ridge baseline and its safe numeric inference interface |
| `models.py` | General named-feature logistic/ridge research, chronological validation, numeric JSON models and optional local ONNX inference |
| `local_inference.py` | Bounded requests to a user-operated tabular/LLM endpoint, explicit signal extraction and target/decision diagnostics |
| `engine.py` | Shared readiness/latency queue, eligible-open execution, proportional/fixed commission, spread/slippage, active-window cash/position accounting, order clocks and metrics |
| `research.py` | Dataset/model orchestration, common clock, result provenance, market/portfolio/inference records and export/rerun configuration |
| `server.py` | Loopback UI, structured HTTP routes, session buffer, origin/Host/token checks and modest single-user operation locks |
| `storage.py` | Explicit local run persistence, content-based record identity and the separately consented Alpha Vantage credential file |
| `rl.py` | Bounded experimental long/cash environment and tabular Q example; optional Gymnasium adapter |

A model produces an explicit intent; it cannot fabricate fills or mutate hidden account internals. Rule strategies, basic models and external inference reuse the same execution/accounting conventions. The chosen generic observation expiry is shared by rule and model orchestration. Different data frequencies still need explicit publication, horizon and stale-value assumptions.

## Model and data scope

Core training is CPU logistic or ridge regression, not a universal neural-training product. Named numeric inputs, fixed categorical hash buckets, small flattened JSON records, selected text measurements and causal transformations are supported. Raw images/audio and arbitrary framework models need user preprocessing or a compatible inference service.

Pretrained numeric JSON is validated rather than executed. Optional ONNX supports a documented one-matrix-input contract on the user's CPU runtime. A chosen local ONNX path can reference large graph/weight files outside the release. Other large or multimodal models can use a user-operated endpoint. Localhost is the endpoint default; remote HTTPS requires an explicit choice. Historical LLM replay does not establish historical model availability or exclude knowledge of future facts.

The native ONNX route is optional and must not be treated as locally verified merely because its integration exists. Consult [implementation status](../IMPLEMENTATION_STATUS.md) for executed test evidence. Installing an extra does not install model weights or imply that every estimator/framework is exposed in the UI.

## Session privacy and persistence

The browser API keeps runs in process memory unless `persist_local` is explicitly true. The session buffer retains up to 20 recent runs and evicts older records above an estimated 50 MB JSON budget, retaining the latest run. Explicitly saved runs live outside source under `HYPOTHESIS_LAB_HOME` or the platform default, and are included in GUI history only when requested.

The research record contains data identity, selected inputs, mapping/transform/model configuration, runtime, warnings, market bars, fills, portfolio ledger and inference diagnostics. A user-initiated save/export can contain imported data and supported model parameters. Credentials are separate inputs and are omitted from research exports. Rerunning an external model may need its original local files, endpoint and a newly supplied session credential.

Optional source requests go directly from the local app to the selected public provider. Model requests go to the user's selected local service or explicitly chosen remote provider. There is no app-operator research service. Provider/model-service retention policies remain those of the selected service. The older Alpha Vantage settings test is a separately consented local-file credential workflow.

## Execution and release boundaries

The simulator covers one instrument, long-only fractional spot holdings and market fills at the first supplied later open eligible after publication, optional inference readiness and order latency. Even a small delay can defer a whole coarse bar; this is not intrabar execution reconstruction. It does not implement synchronized multi-asset portfolios, order books, margin, advanced orders, corporate actions, real-money brokerage or a persistent forward paper-trading service. The original source in `legacy/` is preserved but not imported by the supported launcher; the audit explains why.

The release is source and small redistributable fixtures, not an AI/model appliance. Packaging enforces a 20 MB source ZIP budget and a 10 MB per-source-file budget, with allowlists and exclusions for user datasets, credentials, environments, caches and model weights. Optional runtimes, SDKs and large model files are installed or operated separately by the user.

See [research workflow](research-workflow.md), [model inputs](model-inputs.md), [data sources](data-sources.md), [settings](settings.md) and [implementation status](../IMPLEMENTATION_STATUS.md).
