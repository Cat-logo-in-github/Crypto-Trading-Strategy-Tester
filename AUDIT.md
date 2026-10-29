# Repository audit and architecture decision

Audit date: 2026-10-28. Input: the user's local `exploring-quant-fin.zip`; no replacement repository was downloaded. The original archive remains untouched.

## Decision recorded before implementation

Preserve the original Bitcoin Trading Bot and Research Wing source under `legacy/`, but replace the active historical execution path with a deliberately narrow, tested spot simulator. Keep the separation of data, strategy intent, execution, portfolio accounting, metrics and reporting. The old engine's current-close fills and timestamp-only latency are unsuitable foundations for honest experiments. Do not advertise its broad abstractions as verified capabilities.

Use Python 3.11+ and a standard-library localhost service with a bundled HTML/CSS/JavaScript interface. No frontend build tool, Docker, account, cloud backend or paid service is needed. Standard-library ridge regression gives one auditable CPU ML workflow. Optional heavier model/environment integrations can be added behind extras, after the foundation is sound.

The active simulator supports one instrument, long-only spot exposure, fractional units, next-bar-open market fills, proportional fees and adverse proportional slippage. No shorting, margin, partial fills, order-book simulation, real-money orders or fabricated liquidity model. This explicit scope is preferable to retaining unverified execution modes.

## Evidence from the supplied code

- `legacy/research-wing/analysis/engine/backtester.py`: current candle updates indicators before strategy evaluation (original lines 112-125); matching then uses the same candle close (248-258). This permits a close-informed decision to fill at that close.
- `legacy/research-wing/analysis/engine/execution/matcher.py`: latency alters the fill timestamp while retaining the current price (122-126). Advancing a timestamp does not establish that the price was executable later.
- `legacy/research-wing/analysis/strategies/ml/ml_strategy.py` is empty; there is no implemented training, chronological validation or inference workflow to preserve.
- `legacy/research-wing/analysis/tests/test_closed_trade.py` is a printed example with no assertions. Documentation describes more test coverage than the code demonstrates.
- `legacy/bitcoin-trading-bot/bot/strategy.py` uses a modulo counter. It remains a legacy pipeline testing utility and is not evidence of investment performance.
- The supplied archive contains a development environment, Git history, a local `.env`, logs and downloaded market data. These are excluded from the release. No values from credential files are reproduced here.

Detailed executable findings and a current alternatives comparison are added below as independent audit work completes.

## Retained work and priorities

Original Python modules, interfaces, architecture notes and screenshots are preserved for reference. Legacy examples may need their original dependencies and private/local datasets; they are not the supported launcher. The input ZIP is the preservation copy for excluded local data. New offline fixtures are generated synthetic data with explicit provenance.

Implementation order: validated UTC data and availability-time joins; next-open execution and accounting; cost-compatible benchmarks; guided rule UI and reproducible local runs; purged chronological ML; bounded research extensions; documentation, CI, static Pages and deterministic release packaging.

## Appendix A: independent execution evidence


Audit performed 2026-10-28 against the source extracted from the user's ZIP. The original ZIP was not changed. Paths below refer to original source now preserved under `legacy/` in the deliverable. Findings are source inspection unless an execution result is explicitly supplied.

### Scope and inventory

The ZIP contained 20,513 entries, chiefly Git history and a local environment. Extraction retained 149 project files before excluding local configuration, logs and downloaded datasets from the deliverable. Inspected the root README, Research Wing architecture and implementation, Bitcoin bot, dependency manifests, data adapters/loader/cleaner/downloader, strategy interfaces and implementations, execution and accounting, evaluation, indicators, two test/example scripts, and experiment entry points. No original `LICENSE`, Python distribution metadata, or GitHub Actions workflow was present in the inspected project files. Original dependency manifests are long pinned environment snapshots rather than separated runtime, optional and development groups.

### Concrete defects and directly observed limitations

| Severity | Evidence | Consequence |
| --- | --- | --- |
| High | `legacy/research-wing/analysis/engine/backtester.py:112-125` updates current-bar indicators and obtains a decision; `:248-258` matches at that same candle's close and timestamp. Candle's own docstring defines timestamp as opening time (`models/candle.py:32-33`). | Full-bar information is treated as known at the bar opening and is traded at its already observed closing price. There is no deferred next-bar order queue. |
| High | `engine/execution/matcher.py:122-126` applies a latency timestamp transform, while `:130-167` retains the current price. `backtester.py:273` applies the trade immediately. | Latency changes the label, not when funds/holdings change or which market price is used. Executed reproduction below demonstrates a fill dated after the backtest ending while already affecting its first equity point. |
| High | `backtester.py:136-141` records equity after first execution, `engine/results.py:135-143` declares that first post-fee observation initial equity, and `metrics/returns.py:45-53` computes final/first. | Entry costs on the first bar disappear from reported total return. Two-bar reproduction reported +100% against actual +98.0198% versus starting capital. |
| High | `backtester.py:188-189` copies the positions dictionary without snapshotting Position values; `models/context.py:124-136` stores mappings directly. | Frozen StrategyContext is not a read-only portfolio boundary. Executed assignment to `context.positions['BTC'].quantity` changed the actual engine position to 999. |
| High | `data/loader.py:160-163` reuses `_find_raw_file(symbol, interval)`; `:264-273` selects the first prefix match, and `_load_raw` does not filter requested dates. `force_download` only bypasses the processed-cache fast path at `:82`, then still uses the raw-cache path. | A requested research period or forced refresh can silently use another raw dataset. Provider identity/version/availability is not part of processed-cache identity. |
| Medium | `engine/execution/fees.py:NoFee.calculate` calls `self._validate`, but `_validate` is declared on PercentageFee, not FeeModel or NoFee. | Directly executed zero-cost NoFee path raises `AttributeError: 'NoFee' object has no attribute '_validate'`. |
| Medium | `data/cleaners.py:153-167` and `models/candle.py:63-81` rely on comparisons without finite-value checks. | Executed NaN OHLC passed both cleaner and Candle validation. Candle does not require positive prices. |
| Medium | `data/loader.py:98-101` always passes `interval_ms=60_000`, even when caller chooses another interval. CSV adapter parses naive local datetime; Binance adapter discards close/publication times. | Gap analysis is wrong outside one-minute bars; timestamp availability and timezone conventions are inconsistent. |
| Medium | `engine/benchmark.py:95-120` invests at first close without execution costs. Evaluator `:102-105` uses risk defaults, with `metrics/risk.py:26,79` defaulting to 252 periods/year. | A minute-based crypto strategy is compared with a cost-free benchmark, and Sharpe/volatility use a daily equity annualization factor. Undefined zero-volatility Sharpe is reported as zero. |
| Medium | `strategies/weird/ice_cream_strategy.py:485-537` maps a month's industrial-production value to the first candle of that same month. FRED downloads have observation dates/values, no release-vintage availability. Short windows deliberately time-compress monthly observations from about five years earlier (`:631-728`). | The monthly path uses information before the month is complete. The compressed path is a synthetic event exercise, not evidence of a historical economic relationship. Revised data is not point-in-time data. |
| Medium | `strategies/weird/ice_cream_strategy.py:1147` references `IceCreamSalesStrategy.name`, but the class defined is IceCreamProductionStrategy. | Direct call of `_hold` raises `NameError: name 'IceCreamSalesStrategy' is not defined`. |
| Medium | `bitcoin-trading-bot/bot/trader.py:75-105` divides risk cash by stop distance (units), then treats the result as currency amount at wallet.buy. | ATR position sizing mixes asset units and quote currency. No stop order actually enforces this risk budget. Source inspection; not executed because the bot's dependencies are unavailable. |
| Medium | `bitcoin-trading-bot/bot/paper_wallet.py:37-45` accumulates units but replaces entry price with most recent price, and does not charge costs. | Reported unrealized P&L is wrong if callers add multiple lots. Main Trader currently prevents that scenario, so this is a wallet API defect rather than a demonstrated default-loop error. |
| Availability | `strategies/ml/ml_strategy.py` is zero bytes. There are no implemented ML training/splitting/model persistence or RL environment workflows in the original source. | The original project's ML claim describes planned experimentation rather than a functioning workflow. |
| Testing | `analysis/tests/test_closed_trade.py` is an import-time printed example with no assertions; `dashboard_test.py` launches a dashboard under `__main__`. | Existing files do not constitute an assertion-based regression suite. |
| Packaging | A local `.env`, Git metadata, environment files, logs and downloaded market/alternative datasets were included in the user's ZIP. | Those must be excluded from the release; the audit never printed credential values. Redistribution provenance of original data was not established. |

### Working components worth retaining

- Explicit Strategy -> Signal -> Broker -> Order -> Matcher -> Trade -> Portfolio -> Result -> Evaluator boundaries are reflected in real modules, not only in the architecture diagram. Keep this conceptual separation and the archived source, while replacing defective timing/reproducibility paths in the supported application.
- Frozen Candle and Trade records, immutable result snapshots, broker protocol and separate cost models provide useful extension patterns. They need stronger validation and genuinely immutable strategy views.
- Portfolio applies buy notional plus fees and sell proceeds minus fees; realized P&L is bookkeeping and is not added twice to cash. An executed hand-calculated buy/sell case passed: start 1000, buy 1 at 100 plus fee 1, sell at 120 minus fee 1 -> final cash 1018, gross realized P&L 20, net capital change 18.
- FIFO trade reconstruction proportionally allocates fees to partial closes. The supplied closed-trade example ran and returned gross P&L 20, net P&L 18, holding period one day.
- Rolling SMA has proper warmup and incremental updates. Executed period-3 input `[1,2,3,4]` returned `[None,None,2.0,3.0]`.
- SMA crossover detects actual crossings, records prior values, distinguishes long/short entry and exit intent, and does not directly fabricate fills.
- Provider registration and independent cleaning/reporting are useful ideas; preserve the extension pattern while making datasets typed, point-in-time and identifiable.
- Bitcoin bot is a paper application and contains no real-money execution path in the inspected code. Its counter-driven strategy (`bot/strategy.py:11-29`) must remain explicitly a test utility.

### Execution evidence

Audit interpreter: Python 3.12 on the Windows verification host. The development interpreter is not required by the distributed application.

1. `python -m pytest analysis/tests -q`, from original Research Wing: **not run successfully**, interpreter reported `No module named pytest`. No pass claim.
2. `python -m analysis.tests.test_closed_trade`: **executed, exit 0**, printed a one-unit long trade with gross 20, net 18, one-day holding period. This is a smoke example, no assertions.
3. `python -m analysis.experiments.run`: **attempted, exit 1**, import failed at `analysis/data/downloader.py:25` because `requests` is not installed in the bundled runtime. This establishes an environment/dependency limitation, not a strategy runtime failure. The script also specifies online fetching and dashboard launch, so it is not an offline base example.
4. Standalone import-based accounting/timing/validation probes: **executed, exit 0**, returned the following actual values:
   - NoFee: AttributeError (confirmed defect).
   - First candle 2025-01-01 UTC; 3-day-latency trade dated 2025-01-04 UTC at price 100, but first equity was already 990.0990099009902 from starting cash 1000; second candle 2025-01-02 price 200. Reported total return 0.9999999999999998 versus actual final/1000 minus one 0.9801980198019802.
   - Fee-bearing round trip final cash 1018, gross realized 20, net change 18.
   - StrategyContext mutation propagated quantity 999 into live portfolio.
   - Cleaner retained one NaN OHLC row with zero invalid-row removals; Candle accepted NaN prices.
5. Standalone SMA and IceCream `_hold` probes: **executed, exit 0**. SMA passed hand calculation; `_hold` raised the documented NameError, caught and reported by the probe.

No external market service was queried as part of these probes, and no original `.env` values or bot logs were displayed. Python may have created `__pycache__` files in legacy directories during executed imports; release packaging must exclude them.

### Architectural recommendation

Retain the original work under `legacy/` with attribution and a clear unsupported status. Preserve its useful architecture and demonstrated accounting behavior; replace the supported orchestrator, data boundary, first-equity convention, benchmark execution and reporting in a separately packaged local-first foundation. The cost and integration burden of an institutional multi-language engine is not justified for the first verified single-instrument, spot, next-open simulation. Maintain an explicit small execution interface so a mature engine adapter can be added later without coupling the UI/research configuration to the simulator. Do not claim the original engine is safe merely by repairing the most obvious bug, and do not discard the user's month of source work.

Priorities: point-in-time timestamps and event revisions; next-open order lifecycle with actual fees/slippage and cash constraints; original-capital equity baseline; compatible benchmark; deterministic exported experiment identity; chronological/purged ML splits and safe serialization; offline assertion-based tests; guided UI; CI and clean reproducible packaging. RL and live feeds can remain honestly documented extensions until a real implementation is verified.

### Suspected weaknesses requiring broader validation

Not exhaustively property-tested: partial closes/position flips over long random trade sequences, floating-point tolerances, order idempotency, large data/memory behavior, every indicator's initialization convention and corporate-action handling. No supported multi-asset synchronized mark-to-market, margin, short borrow model, survivorship correction, exchange calendars or corporate-action pipeline was found. These are scope limits; do not invent evidence that the current software produces correct results for those cases.

## Appendix B: current alternatives and provider research


Verified against primary sources on 2026-10-28. Availability and terms can change. This research did not install or benchmark these engines, use credentials, or execute financial orders. Integration and memory assessments below are engineering judgments, not vendor benchmark claims.

### Execution-engine alternatives

| Candidate | Verified facts | Integration assessment for this renovation |
| --- | --- | --- |
| QuantConnect LEAN | Engine source is Apache-2.0, event driven, modular, C#/Python. Its official README routes local research, backtests and optimization through Docker. Current CLI installation documentation requires membership in a paid-tier organization, and its getting-started process uses login. Source-engine licensing and CLI service requirements are separate matters. | Strong future execution adapter for broader asset models. Making the current CLI the base launcher violates this mission's no mandatory subscription/account/Docker requirements. Independent engine builds remain possible but need a separate .NET/Python bridge, configuration and data integration effort. Do not state that LEAN source itself requires payment. |
| NautilusTrader | LGPL-3.0 engine with Rust native implementation. Latest 2.x documentation targets CPython 3.13-3.14 and 64-bit platforms, Ubuntu glibc >=2.35. At verification, 2.x is a release candidate while a plain pip install selects stable 1.x with a different API. Release 2.0.0rc7 is dated 15 October 2026. | Strong candidate for event-driven, multi-instrument and detailed execution work. Native wheel compatibility, version/API selection, venue/instrument schemas and data wrangling increase base-install and adapter scope. CPU is sufficient for engine use; no universal memory minimum was established from these sources. |
| backtesting.py | AGPL-3.0, Python >=3.9. Current setup declares NumPy, pandas and Bokeh. The project exposes backtest strategy interfaces, plotting, commission/spread and fractional-trading helpers. Its changelog, rather than GitHub Releases (currently empty), is the maintenance reference. | Simpler bar-backtesting integration than the larger engines, but brings scientific/plotting dependencies and AGPL obligations. Alternative-event availability and the guided research workflow still require app-layer implementation. Consider a separately documented adapter rather than silently embedding under a permissive application license. |

Primary sources:

- [LEAN repository and license](https://github.com/QuantConnect/Lean)
- [LEAN official README](https://github.com/QuantConnect/Lean/blob/master/readme.md)
- [LEAN CLI installation requirements](https://www.quantconnect.com/docs/v2/lean-cli/installation/installing-lean-cli)
- [LEAN CLI getting started](https://www.quantconnect.com/docs/v2/lean-cli/key-concepts/getting-started)
- [NautilusTrader source and license](https://github.com/nautechsystems/nautilus_trader)
- [NautilusTrader installation and compatibility](https://nautilustrader.io/docs/latest/getting_started/installation/)
- [NautilusTrader maintained release history](https://github.com/nautechsystems/nautilus_trader/releases)
- [backtesting.py dependency and license declaration](https://github.com/kernc/backtesting.py/blob/master/setup.py)
- [backtesting.py public documentation and licensing](https://github.com/kernc/backtesting.py/blob/master/backtesting/__init__.py)
- [backtesting.py changelog](https://github.com/kernc/backtesting.py/blob/master/CHANGELOG.md)

Decision recommendation: keep the existing code available for audit and migration, preserve useful indicator and interface concepts, and implement a deliberately bounded spot long-only bar simulator whose execution/accounting can be proved with hand-calculated fixtures. This is a narrow replacement of defective execution, not a claim to replace mature order-book infrastructure. Make the shared dataset, decision and result contracts explicit so a future execution adapter can be added without rewriting the research UI. Reject unsupported assets/order types clearly.

### ML, reinforcement learning, features and tracking

- **scikit-learn:** BSD-3-Clause; provides established regression/classification, forests, boosting, preprocessing, feature selection and feed-forward neural networks. Requires compiled scientific dependencies (NumPy/SciPy and others); wheels are preferable to building locally. Keep it optional. Current main-branch requirements can exceed older supported releases, so pin and test a compatible optional range rather than assuming all Python versions share the latest dependency set. [Source/license/dependencies](https://github.com/scikit-learn/scikit-learn), [installation](https://scikit-learn.org/stable/install.html), [model families](https://scikit-learn.org/stable/).
- **Safe persistence:** sklearn warns that pickle, joblib and cloudpickle can execute code when loading and cross-version loading is unsupported. A small linear model can be persisted as validated JSON coefficients, scales and feature definitions without executable deserialization; established ONNX/skops are other possible future choices with their own validation needs. [Official persistence guidance](https://scikit-learn.org/stable/model_persistence.html).
- **Stable-Baselines3:** MIT; current installation guide requires Python >=3.10 and PyTorch >=2.8. This is a substantial optional dependency, not appropriate for the base installer. CPU examples are viable; GPU acceleration should be detected rather than promised. [Maintainer package metadata](https://pypi.org/project/stable-baselines3/), [installation](https://stable-baselines3.readthedocs.io/en/master/guide/install.html).
- **Gymnasium:** standard environment protocol separates `terminated` from time-limit `truncated`; `step` returns observation, reward, these two flags, and info, while reset returns observation and info. Follow these semantics if exposing a compatible environment; do not label a small custom interface Gymnasium-compatible without checking it. [Environment API](https://gymnasium.farama.org/api/env/).
- **Optuna:** MIT; appropriate for later bounded hyperparameter optimization. It cannot prevent test-period selection or leakage by itself. The application must enforce train/validation-only search and record the trial count. [License](https://github.com/optuna/optuna/blob/master/LICENSE), [research paper](https://arxiv.org/abs/1907.10902).
- **MLflow:** Apache-2.0, available self-hosted. Useful for richer experiment tracking, but a local versioned JSON record plus content hashes can meet the initial single-user requirement with much less operational and dependency burden. This is an integration judgment. [Project's self-hosted offering](https://mlflow.github.io/mlflow-website/).

Ordinary bundled samples should fit modest CPU hardware. No defensible universal RAM minimum exists independently of dataset row count, feature count, search budget and estimator choice. Document actual bounds and tested sample sizes; do not invent GPU requirements or vendor performance claims.

### Open-Meteo historical weather

- Historical API is based on reanalysis, with ERA5 coverage from 1940, ERA5-Land from 1950 and newer IFS data from 2017. This is reconstructed/revised weather, not proof of what a trader knew at the observation timestamp. [Historical API](https://open-meteo.com/en/docs/historical-weather-api).
- Free API is noncommercial, without a key. Terms state fewer than 10,000 calls/day, 5,000/hour and 600/minute; service availability is not guaranteed. Commercial use needs an appropriate plan or a separately operated instance. Data license is CC BY 4.0, which permits reuse with attribution; service-access restrictions and data licensing differ. [Terms](https://open-meteo.com/en/terms), [data and service overview](https://open-meteo.com/).
- Use a backend HTTPS request with fixed provider URL and explicit geographic coordinates/dates. Browser CORS is not relied on. No CORS guarantee was verified. Record provider attribution, retrieval time and a conspicuous non-point-in-time warning. A configurable conservative availability delay does not repair historical revisions; use fixtures with known publication times for leakage tests.

### Kraken read-only public OHLC

- Public GET endpoint is `/0/public/OHLC`, without private account authentication. It returns at most 720 recent entries; older bars cannot be recovered by changing `since`. The last entry is always the current uncommitted interval and must be excluded when requiring completed bars. [Official OHLC contract](https://docs.kraken.com/api-reference/market-data/get-ohlc-data).
- Public OHLC limits apply by IP and pair. Official support, updated 1 October 2026, says one request per second or slower remains within rate limits. Manual refresh with a substantially longer minimum interval is conservative; handle provider errors and network failure without disabling historical work. [Rate limits](https://support.kraken.com/gb/articles/206548367-what-are-the-api-rate-limits-).
- API use is subject to Kraken terms, including commercial use of public endpoint data. Public accessibility is not an unrestricted redistribution license. Do not bundle fetched Kraken data in the release or advertise commercial data redistribution. [API introduction and terms reminder](https://docs-legacy.kraken.com/api/docs/guides/global-intro/), [global terms](https://www.kraken.com/legal/global-terms).
- Label the interface as a polled public exchange snapshot, with last fetch and last completed candle timestamps. It is not a guaranteed low-latency stream. Backend requests avoid dependence on browser CORS; CORS behavior was not independently verified. Never call order/account endpoints in this renovation.

### Alpha Vantage optional credential example

`GLOBAL_QUOTE` accepts one symbol and a required API key. JSON and CSV are documented. Standard quote freshness is end of each trading day; real-time or 15-minute delayed US quotes require premium entitlement. A successful connection test must therefore say **end-of-day quote snapshot**, not live quote. Handle error/Information/Note responses including invalid keys and quotas, and never expose the URL containing the key in logs or exports. [Quote API documentation](https://www.alphavantage.co/documentation/#latestprice).

The published standard free quota is 25 API calls/day. The support page discusses unlimited requests for verified open-source/educational projects, but that must not be assumed for a user who simply installs this repository. Provider quota terms still apply to connection tests. [Support/key registration](https://www.alphavantage.co/support/), [premium/quota description](https://www.alphavantage.co/premium/).

An optional masked settings input with an explicit save action and remove control fits the mission. Store under user-selected local application state, encrypted with Windows DPAPI when available or owner-readable storage with a clear limitation elsewhere. Send a key only to the explicitly selected fixed Alpha Vantage endpoint. Core research never requires this key.

### GitHub Pages workflow

Official current custom-workflow docs demonstrate `actions/configure-pages@v5`, `actions/upload-pages-artifact@v4`, `actions/deploy-pages@v4` and `actions/checkout@v6`. Deploy job needs `pages: write`, `id-token: write`, a build dependency and `github-pages` environment. Set repository Settings > Pages > Source to GitHub Actions once; public repositories can use Pages on GitHub Free. [Custom workflow documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages), [setting the publishing source](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

At verification, releases also exist for [upload-pages-artifact v5](https://github.com/actions/upload-pages-artifact/releases), [checkout v7](https://github.com/actions/checkout/releases) and [setup-python v7.1.0](https://github.com/actions/setup-python/releases). The documented prior major versions remain usable. A generated static relative-link site avoids repository-subpath assumptions. Remote Actions execution and actual Pages publishing cannot be verified by a local build alone.

## Version 0.2 implementation decisions (2026-10-29)

The follow-up scope generalizes external features instead of adding a privileged weather or maritime pathway. Public-catalog search proposes candidates; exact measurements, licensing and publication history remain reviewable. Private product sales require an authorized owner export/API. Generic CSV/JSON and HTTPS GET connectors map numeric, categorical or explicitly measured text fields, with acquisition-time availability unless the user supplies publication history or declares a historical-lag assumption. No catalog is represented as a universal source of all facts.

Small logistic/ridge models can predict an arbitrary mapped quantity and convert the output into an explicit trade policy. Chronological purging, training-only normalization and validation-only selection are shared with uploaded numeric JSON inference. Large/custom models stay in the user's own service; optional ONNX uses its separate runtime. Executable pickle/joblib/Python uploads are not accepted. Historical LLM replay exposes pretraining leakage and reported-token limitations; forecast accuracy and market profit remain distinct diagnostics. See [model inputs](docs/model-inputs.md) and [data sources](docs/data-sources.md).

Generic source/model credentials and experiments now default to process memory. Local save/export is explicit. There is no project-owner data receiver. Requests chosen by the user go directly from the local process to that provider; the provider's own retention is outside this application's control.

For nontechnical visitors, Pages is a download hub linking to a separate portable Windows ZIP with a native launcher and private official CPython runtime. The small source ZIP excludes this runtime and model weights. The release workflow downloads the official [Windows embeddable runtime](https://www.python.org/downloads/windows/), pins its SHA256, and checks the extracted executable before uploading. Runtime/app notices accompany the portable build. Local checks establish packaging behavior; publication still requires the repository owner to push and release.
