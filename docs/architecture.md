# Actual system architecture

The supported v0.4 package is `src/hypothesis_lab`, a student project for historical strategy research and simulated paper trading. A standard-library Python service binds to `127.0.0.1` and serves the guided studio and dark market terminal. There is no Node build step, mandatory cloud service, account, telemetry or paid core dependency. GitHub Pages serves the static landing page and documentation, not research execution.

## Shared research flow

```text
Question -> reviewable data requirements and candidate-source search
  -> local CSV/JSON, selected HTTPS provider or synthetic fixture
  -> immutable UTC market bars and availability-aware observations
  -> chosen numeric/categorical/text inputs and causal transformations
  -> rule intent, trained baseline or user-model inference
  -> explicit output-to-trade policy
  -> selected bar, quote/depth/trade or linked-contract execution, costs and accounting
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

The base simulator covers one long-only fractional spot instrument at eligible supplied opens. The optional `microstructure` backend uses observed quote/depth/trade receipt events for partial fills and explicit passive-queue assumptions. The `portfolio` backend uses signed multi-contract positions, shared-currency collateral, observed quotes and declared funding/dividend/margin/settlement/exercise events. See [replay](execution-replay.md) and [linked contracts](linked-contracts.md). Neither reconstructs missing intrabar or exchange-priority evidence from OHLC. There is no real-money brokerage, broker-exact portfolio margin, cross-currency collateral, automatic stochastic assignment or persistent forward trading service. The original `legacy/` source is preserved but not imported by the supported launcher; the audit explains why.

Optional `compute` sends explicit user tasks/local manifests or authorized inline tables to a user-operated extractor/trainer. Results are validated structured data and reusable prediction configuration. No generated Python, weight installation or operator backend is involved. `scenarios` supplies fixed synthetic pipeline trials, while the dated public-data report is a separately labeled retrospective study. `validation` summarizes conditional return uncertainty with paired blocks, not edge certification.
