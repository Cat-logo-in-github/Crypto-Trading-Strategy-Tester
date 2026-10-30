# Implementation status - v0.4

This describes the local v0.4 student project for historical strategy research and simulated paper trading. It sends no real orders and does not promise a scientifically conclusive trading edge. The user's original ZIP was audited without downloading a replacement repository. Original source remains under `legacy/`; its local `.env`, logs, downloaded datasets, Git history and development environment are excluded from the release.

Exact final test counts, artifact hashes and clean-extraction results belong to the delivered verification report. The final archive check is a release step, not something implied by code existing or a workflow being configured.

## Available workflows and boundaries

| Capability | Status | Actual scope |
| --- | --- | --- |
| Windows desktop download | Implemented; local portable/launcher checks executed | Extract the separate Windows ZIP and open `Hypothesis Lab.exe`; private official CPython runtime, no system Python or terminal needed for visitors |
| Local research application | Implemented | Loopback Python service and bundled browser UI; no mandatory account, hosted app backend, telemetry or paid service |
| General data discovery | Implemented | Bounded catalog discovery across Socrata, World Bank, NASA CMR, European and humanitarian catalogs; semantic direct/related/weak ranking, explicit metadata/binary-reference limits and custom HTTPS APIs |
| Alternative data | Implemented | CSV/TSV/JSON/NDJSON/GeoJSON Point/properties, quality reports, suggested/composite dates, entity filters, numeric/boolean fields, categorical hashing, explicit text equality/measurements and causal aggregation/transformations |
| Time and publication semantics | Implemented and covered by tests | Observation/publication separation, revisions, explicit timezone/lag assumptions and shared observation expiry in rule/model orchestration |
| Rule strategies | Implemented | AND/OR conditions over market indicators or mapped `event:field` observations, supported sentence patterns, visual controls and editable JSON |
| Guided algorithm setup | Implemented | Idea → Data → Signal → Period → Run; separate entry/exit conditions, bounded causal expression chains, geospatial conditions, preview and optional user-LLM draft; no executable generated Python |
| Historical duration | Implemented | UTC start/end dates or recent-bar windows, completed-bar eligibility, earlier indicator warmup and accounting reset at the active window; trained models trade in the held-out subperiod |
| Core supervised training | Implemented and covered by tests | CPU logistic probability or ridge numeric baseline on named inputs and an independently selected external/market target; chronological splitting/purging and training-only scaling |
| Pretrained numeric models | Implemented and covered by tests | Validated JSON logistic/ridge/linear parameters, explicit input mapping/output policy, declared training-provenance checks; no pickle/joblib/Python execution |
| Optional ONNX | Integration implemented; native local execution not verified | Optional CPU numeric-matrix adapter, small uploads or explicitly selected local graph/weights; separate advanced Python setup, not bundled in the portable Windows edition |
| User model/LLM services | Implemented and covered by bounded/mocked/local-endpoint tests | User-operated tabular or OpenAI-compatible endpoint, optional strict data-plan proposal, JSON numeric output, defined text signals or reported token counts; remote HTTPS requires an explicit choice |
| Inference-to-trade policy | Implemented | Explicit output/comparison/threshold, target weight or cash buy, false-condition hold/exit; intents use the selected shared execution backend; linked derivatives require explicit signed legs and target scaling |
| Market/portfolio inspection | Implemented | Dark OHLC candles, buy/sell markers, range/zoom, all-fill pagination/filtering, linked cash/position/cost inspection, equity/drawdown/exposure and inference/target/market diagnostics |
| Execution and metrics | Implemented and covered by independent expectations | Three explicit execution paths: bar spot, supplied quote/depth/trade single-instrument replay, and shared-currency signed multi-contract ledger. Base bar path retains cash limits, proportional/fixed commission, full spread/adverse slippage, data/processing/submit delays, eligible-open fills, order clock events and marked accounting |
| Dated cost scenarios | Implemented | Official 2026 venue fee snapshots with scope and primary links; spread, slippage, processing and hardware/network timing assumptions remain separately labeled and editable |
| Session/privacy model | Implemented | UI runs are in RAM by default; up to 20 recent runs with a 50 MB older-record eviction budget, retaining the latest record; explicit local save/export choices |
| Credentials | Implemented | Generic source/model keys are separate session inputs and excluded from research exports; the original Alpha Vantage test retains a separately consented local-key file |
| Exploration/RL | Bounded/experimental | Original market-feature subset search and a small Python tabular-Q environment/example; no universal feature search, deep-RL UI or performance claim |
| Pages, CI and releases | Configured, not remotely published here | Static landing/docs deployment, core/optional CI, small source ZIP, separate Windows ZIP and checksum release assets |

## Questions the broader workflow can represent

A measurement such as sales, traffic, city growth, shipping activity or defined text output can be an input, target or observed rule condition. The trained/predicted quantity can differ from the asset being traded. A user can specify "if the probability of this quantity increasing exceeds 0.5, buy $100; otherwise hold" and inspect the resulting inference, intent, fill and portfolio state.

The built-in multi-domain demonstrations are explicitly synthetic: ice-cream/merch/rubber-duck sales, traffic, urban growth, shipping, weather, moon phase and day type. They establish software behavior, not a real dataset relationship. Private commercial sales require an owner's authorized export or API. A permit, shop location or inspection count is a different proxy and is not silently treated as actual sales.

Mapping supports publication columns, conservative acquisition-time availability or an explicit assumed historical lag. Numeric/boolean inputs, fixed categorical buckets, defined text equality/count/contains/length features and trailing lag/difference/proportional-change/mean/sum/z-score transforms are supported. Raw multimodal inputs and arbitrary frameworks require user preprocessing or a compatible inference endpoint. Satellite metadata/current orbital references are ranked above geographic-only alternatives, but are never represented as historical satellite-pass events without appropriate extraction/history.

## Evidence actually obtained

### Original repository

The original closed-trade example and SMA warmup were executed. Reproductions confirmed same-close execution, timestamp-only latency, first-fee return bias, missing `NoFee` validation, mutable position context and NaN acceptance. One legacy network example stopped at a missing `requests` dependency and was not reported as passing. See `AUDIT.md` for evidence and the architecture decision.

### Active application and scientific contracts

Automated coverage includes hand-calculated accounting, seeded portfolio reconciliation, UTC/availability/revision/expiry rules, the weather/SMA example, generic CSV/JSON and derived features, chronological ML purging, held-out perturbation checks, numeric model import/inference, RL transitions, provider/endpoint failures, explicit persistence, real loopback HTTP behavior and archive/site safety.

The earlier rule/model expiry discrepancy was independently reproduced and corrected: a chosen 8,760-hour external-observation lifetime now produces 365 model-eligible daily bars and 365 matching rule fills in that regression case. UI review also corrected saved-run browsing, preservation of model field/target choices, derived input choices, old-record chart clearing and compatible inspection request limits.

The delivered report records the current full-suite results rather than retaining the earlier v0.1 count. Ruff, formatting, typing, distribution/static builds and clean-copy checks are release checks; final results are reported only after execution.

Version 0.4 adds an independent [engine audit](docs/engine-audit-2026.md), including corrected source-name collisions, explicit active-window/once-state behavior, delayed-order eligibility, tiny fractional fills, fixed-fee constraints and undefined risk metrics. New signal tests exercise hand-calculated trailing math, missingness, geographic conditions, prefix causality, rejected executable expressions, algorithm planning and session-only HTTP previews. The latest GitHub cooldown regression distinguishes no prior request from a real time-zero request; it was reproduced before correction.

### Real keyless source probes

The source work obtained real responses for three deliberately small probes:

- Public Socrata traffic discovery/download: three Calgary rows.
- World Bank USA urban-growth indicator: three rows.
- IMF PortWatch daily port activity: ten rows.
- NASA CMR satellite/orbit metadata, European traffic catalog and HDX population queries: verified bounded implemented catalog responses, with downloadable supported tables distinguished from imagery/HTML/large binary references.

These verify that those selected public requests worked at the time of testing. They do not establish unrestricted access, guaranteed future uptime, full historical coverage or redistribution rights for every dataset. Other provider failures and key-handling paths are exercised with controlled responses; no credentialed commercial entitlement is claimed as verified.

Revised World Bank/PortWatch data is not a point-in-time publication archive. Conservative acquisition-time mapping blocks earlier hypothetical use; an explicitly chosen lag is only an exploratory scenario. Slow annual indicators also need an appropriate market period, horizon and expiry rather than an automatic daily-trading interpretation. Open-Meteo reanalysis has analogous historical-vintage limits; its free hosted API remains subject to provider terms.

### Portable Windows checks

The local portable build uses the verified official x64 **CPython 3.14.10 embeddable runtime** separately from the developer's system Python. The real launcher/portable HTTP/model smoke path and native launcher **Quit** behavior were exercised locally. The source core is also exercised on this Windows host with Python 3.12.

The Windows release workflow pins the official runtime URL and SHA-256, builds the small launcher/private runtime distribution, extracts its exact ZIP and invokes its smoke path. Those local checks do not imply that the remote workflow or GitHub download asset has already been published.

The Windows app has a 25 MiB release budget. The separate source ZIP has a 20 MB budget and a 10 MB included-source-file ceiling. Environments, SDKs, user data and model weights are not bundled in the source ZIP; the Windows package adds only its private portable runtime and required app/license files, not a heavy AI stack.

### Optional native components

Native ONNX inference was **not verified locally**: the optional runtime/graph dependencies were not available, and their download attempt did not succeed. Corresponding optional native tests are skipped when dependencies are missing, not counted as native passes. A separate CI job explicitly installs/requires the runtime and graph packages before executing a real self-contained graph test; that configured remote job is not claimed as executed here.

The earlier optional Gymnasium 1.4 environment checker and complete 40-step adapter episode did execute successfully. The checker warned about intentionally unbounded return/gap observation ranges. The current release report distinguishes this earlier native adapter evidence from final core regression results.

## Persistence and user control

New browser runs default to session memory. The shared save checkbox is an explicit opt-in to disk persistence; **Include explicitly saved local runs** exposes those records for View/Rerun after restarting. Saved runs use `HYPOTHESIS_LAB_HOME` or the documented platform state directory. User-initiated exports can contain imported data, numeric model parameters and configuration.

Generic source/model credentials are not research fields, export keys or an app-operator account. Localhost model inference is the default; remote provider use requires an explicit choice and remains subject to that provider's own retention, quotas and charges. The legacy Alpha Vantage credential-file workflow is a separately consented exception: Windows DPAPI, or owner-restricted plaintext on other platforms. A separate Windows DPAPI roundtrip was executed previously.

Model weights stay under user control. Uploaded numeric JSON can be exported intentionally; local ONNX paths require the original files when rerun, and endpoint replay requires the original service and any newly supplied session key. Historical LLM replay happens now, can include future pretraining knowledge and does not establish historic model availability. Measured current inference duration is replayed into order readiness by default, with an explicit disable option; it is a present-day timing scenario, not proof of historical hardware/model availability. Token counts are used only when reported by the endpoint.

## Remaining limits and final-release boundary

- Broad data plumbing is not universal data availability. A question still needs relevant authorized measurements, correct geography/units, sufficient overlapping history and a supported representation. Catalog search and optional LLM planning propose candidates; they do not verify an economic hypothesis.
- Core training is logistic/ridge, not general deep learning, sequence-model training or an automated causal-discovery platform. Optional extras do not automatically add every framework to the UI. The portable edition uses numeric JSON or user endpoints; advanced native ONNX requires its own Python/runtime setup.
- The base bar backend remains long-only spot. Optional observed-event replay and the signed linked-contract ledger extend this with partial liquidity and explicit margin/financing/corporate cash flows. No real-money brokerage, exact venue priority/portfolio margin, tax or automatic survivorship/corporate-action reconstruction is claimed. Each selected path records its own assumptions and end-position handling.
- Persistent forward paper trading is deferred. Public snapshots are labeled completed/delayed/revised as appropriate and are not silently represented as streaming real-time exchange data.
- Interactive market research is bounded to 5,000 bars; basic feature search is bounded separately, and endpoint request/token budgets are explicit. Some rule construction is quadratic. Large workloads belong in a user-controlled pipeline/service.
- Chronological purging and training-only preprocessing do not establish statistical independence or a trading edge. Repeated validation searches, carried sparse values and comparisons can overfit.
- The portable launcher is unsigned. Native ONNX and configured Linux/Python CI matrix jobs are not claimed as locally executed merely because their workflow exists.
- No remote GitHub Pages deployment, release publication or credentialed premium feed was performed here. Final source/Windows extraction, smoke results, archive sizes/hashes and exact test totals are recorded in the delivered verification report after execution.

## Launch and publication

Windows visitors download **Hypothesis-Lab-Windows.zip**, extract the complete folder and open **Hypothesis Lab.exe**. No system Python or terminal is required. Developers can install source with `python -m pip install -e .` and launch `python -m hypothesis_lab`.

The owner uploads the extracted source contents (including `.github`) to the repository, selects **Settings > Pages > GitHub Actions**, then publishes a normal versioned release such as **v0.4.0** targeting the updated commit. The workflow attaches stable source/Windows ZIP names and checksum assets when its jobs finish; a normal branch push intentionally skips publication. See [release instructions](docs/releasing.md), [Signal Studio](docs/signal-studio.md), [research walkthrough](docs/research-workflow.md) and [architecture](docs/architecture.md).


## Version 0.4 integration and audit

New modules are `compute`, `microstructure`, `portfolio`, `portfolio_templates`, `scenarios` and `validation`. See [linked contracts](docs/linked-contracts.md), [execution replay](docs/execution-replay.md), [compute integration](docs/compute-integration.md) and [scenario lab](docs/scenario-lab.md). The original single-instrument/long-only restriction now describes the **bar backend**, not every execution path.

The independent portfolio audit reproduced liquidation replacement, discarded pre-window margin schedules, illegal early European/physical cash-option exercise and closed-profit-factor entry-fee omission. Tests in `test_portfolio_audit.py` cover the corrections. Additional tests hand-calculate funding, multipliers/premiums, dividend ownership/payment, short borrowing, settlement, assignment, partial displayed liquidity, data clocks, fees and insolvent partial liquidation. Rolling arithmetic/threshold precision and future-condition/endpoint replay regressions are in `test_research_contracts.py`.

The user compute contract has real loopback HTTP extraction/training/evaluation and prediction-reuse tests. It transports explicit metadata/finite structured results, not arbitrary executable uploads. A user service must already be implemented/running for its own raw formats/framework. Core numeric training is built in. Current tabular services can process a selected full history in one bounded batch; LLM replay retains a separate per-call budget. Declared pretraining boundaries are checked, but their truth cannot be established by this app.

Five actual public-data exploratory runs use real Coinbase BTC-USD, Wikimedia, Open-Meteo and USGS observations with explicit vintage/availability limitations. [The report](docs/public-strategy-results.md) distinguishes these from the synthetic software fixtures. No real historical derivatives/quote tape or private commercial dataset was provided. Venue-exact portfolio margin, inverse/quanto settlement, cross-currency collateral, stochastic assignment and future profitability are not claimed.
