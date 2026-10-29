# Hypothesis Lab

A free, local-first **student project for historical strategy research and simulated paper trading**. Version 0.3 guides an unusual idea through data, signals, historical duration, execution assumptions and an inspectable experiment. No real orders, account, app-operated backend or mandatory AI service.

## Windows: download, extract, open

[Download Hypothesis Lab for Windows](https://github.com/Cat-logo-in-github/Crypto-Trading-Strategy-Tester/releases/latest/download/Hypothesis-Lab-Windows.zip)

1. Download **Hypothesis-Lab-Windows.zip** from the published release.
2. Extract the whole ZIP into a folder on your computer.
3. Open **Hypothesis Lab.exe** inside that folder.

The Windows package includes its portable Python runtime. You do not need to install Python, open a terminal or edit configuration files. The application opens a browser interface on your computer; use **Stop app** to stop its local service. Keep the extracted files together.

The download link becomes available after the repository owner publishes a release containing that asset. This source renovation does not itself imply a public release or a deployed website. [View release availability](https://github.com/Cat-logo-in-github/Crypto-Trading-Strategy-Tester/releases).

[Source ZIP for developers](https://github.com/Cat-logo-in-github/Crypto-Trading-Strategy-Tester/releases/latest/download/hypothesis-lab.zip) · [Full research walkthrough](docs/research-workflow.md) · [Implementation status and actual verification](IMPLEMENTATION_STATUS.md)

## Follow the question

The platform is not limited to temperature. It separates the quantity you want to measure, the outcome a model predicts and the market instrument you choose to trade.

- **Discover or import data.** Search across public catalogs with direct/related/weak ranking, or fetch your documented HTTPS API. CSV, TSV, JSON, NDJSON and GeoJSON Point/properties have bounded interpreters. Relevant satellite sources precede location-only alternatives, while imagery/orbital references disclose that historical pass extraction is still required. Private data needs an authorized owner export/API and your own session key if applicable.
- **Review a suggested interpretation.** Common and composite dates, wide/long tables, entity filters, explicit text matches and UTC event aggregation have guided mappings and quality reports. Source publication history and assumed lags remain explicit.
- **Make the algorithm precise.** Separate entry and exit conditions, numeric/text-derived signals, trailing calculations, geographic boxes/distances and bounded expression chains can become trading rules or model inputs. Describe a simple algorithm, use the visual conditions, or ask your optional LLM for a reviewed draft. Missing definitions remain unresolved; no arbitrary generated Python is executed. See [Signal Studio](docs/signal-studio.md).
- **Train or bring a model.** Core CPU logistic/ridge baselines accept arbitrary supported named inputs and targets with chronological evaluation. Upload a numeric JSON model, use optional ONNX, or connect a model/LLM service you operate. Define the exact inference-to-trade condition, including a probability threshold or a reported LLM token-count signal.
- **Inspect the market.** Candles, buy/sell markers, zoom and time ranges connect to cash, positions, equity, drawdown, fees and slippage. The full paged blotter and inference-to-decision table help explain why an accurate external forecast can still support an unprofitable trade.
- **Choose the test period and execution assumptions.** Dates/recent bars, actual bar duration, commission, fixed charges, full spread, slippage, processing/data delay and order latency are editable. Dated 2026 venue profiles cite official commissions; hardware/network/spread assumptions are separately labeled. Delays move fills to an eligible supplied open. Indicators retain earlier warmup without placing pre-window orders.
- **Choose what to retain.** Runs stay in RAM by default. Explicit local saving and exports are optional. Source/model requests originate on your computer; no app-operator backend receives the data or keys.

Try the labeled synthetic examples: ice-cream sales, a merch drop, traffic, urban growth, shipping, rubber ducks and moon phases. These teach the workflow; they are not actual economic observations or evidence of a trading edge. A testable question still needs relevant, authorized data and enough overlapping history. Catalog search does not guarantee an exact source for every idea.

## Optional models and connections

Large model weights, SDKs and heavy ML runtimes are **not** included in the small source ZIP or silently downloaded. The portable Windows runtime is a separate distribution from that source archive. Users install optional ONNX support or operate their own model service as needed; a local ONNX path can refer to their existing model files. Unsupported framework or multimodal models need compatible preprocessing or an inference endpoint.

Localhost is the model-endpoint default. A remote HTTPS provider requires an explicit choice, receives the selected inputs and may charge the user. Historical LLM replay can contain future knowledge and is not verified out-of-sample history. Token signals require provider-reported counts; they are not estimated silently. Measured current service inference duration can be replayed as an explicit timing scenario; it is not proof of historical model availability or hardware performance.

Most source/model keys are session inputs and are omitted from experiment exports. The older Alpha Vantage test retains a separately consented local-key save option. See [settings and retention](docs/settings.md), [data sources](docs/data-sources.md) and [model inputs](docs/model-inputs.md) for exact supported behavior and limits. Native ONNX integration is optional; the status document distinguishes implemented adapters from executed native tests.

## Run from source: developers, macOS and Linux

The source workflow uses Python **3.11+**. From the extracted source folder, create a virtual environment with `python -m venv .venv`; activate `.venv\Scripts\activate` on Windows or `source .venv/bin/activate` on macOS/Linux, then:

```console
python -m pip install -e .
python -m hypothesis_lab
```

The service binds to `127.0.0.1`. Use `python -m hypothesis_lab --port 8765 --no-browser` for manual browser launch. Stop with Ctrl+C or **Stop app**. The core has no runtime dependencies; initial installation may obtain build tooling. A direct offline source launch can use `PYTHONPATH=src` instead of installation.

```console
python -m hypothesis_lab sample --output sample-result.json
python -m hypothesis_lab ml --output ml-result.json
python -m unittest discover -s tests -v
```

The bundled market and world-signal fixtures are synthetic and redistributable. The original five-market-feature ridge baseline and experimental Python RL environment remain available; optional extras do not imply a general neural-training platform.

## Documentation and release

- [Quickstart](docs/quickstart.md), [research walkthrough](docs/research-workflow.md) and [architecture](docs/architecture.md)
- [Rule development](docs/strategy-development.md), [model inputs](docs/model-inputs.md) and [extension APIs](docs/api/index.md)
- [Data discovery and connectors](docs/data-sources.md), [data contracts](docs/data-providers.md) and [settings](docs/settings.md)
- [Backtesting methodology](docs/backtesting-methodology.md), [ML baseline](docs/ml-research.md) and [experimental RL](docs/reinforcement-learning.md)
- [Signal Studio and historical windows](docs/signal-studio.md) and [independent engine audit with 2026 cost sources](docs/engine-audit-2026.md)
- [GitHub Pages, CI and packaging](docs/releasing.md), [audit](AUDIT.md) and [verified implementation status](IMPLEMENTATION_STATUS.md)

Build the public documentation and small source release with:

```console
python scripts/build_site.py
python scripts/package.py
```

These produce `dist/site/` and `dist/hypothesis-lab.zip`; the latter excludes keys, user datasets/state, environments, caches, Git history and model weights. Source release budgets are 20 MB per ZIP and 10 MB per included file. The Windows application is a separate portable-runtime artifact, published under the stable download name above.

For GitHub Pages, push the extracted source contents and choose **Settings > Pages > Source > GitHub Actions**. Then publish a normal release tagged **v0.3.0**, targeting the updated source commit. The release workflow builds and attaches both ZIPs; the Pages download button uses the Windows release asset. An ordinary branch push builds artifacts and intentionally skips release publication. After publication, this local build folder can be deleted: GitHub hosts the site, documentation and downloads independently.

## Scope and attribution

Execution is one long-only spot instrument with fractional next-open fills, explicit costs and cash constraints. There is no real-money execution, order-book/liquidity model, margin, corporate-action or tax model. Final holdings are marked at the last close rather than forcibly liquidated. Repeated selection can overfit historical results; prediction accuracy does not establish profitability.

Fills use supplied bar opens only. A small positive latency can skip an entire coarse bar; the app does not reconstruct millisecond prices from daily OHLC. Current commission snapshots are not historical vintage fees. Binary/unstructured data needs a user-controlled extraction/model pipeline that emits supported timestamped signals. These boundaries prevent the software from claiming scientifically conclusive or real-exchange accuracy it has not established.

The original Bitcoin Trading Bot and Research Wing source is preserved under [`legacy/`](legacy/). [AUDIT.md](AUDIT.md) explains the evidence-based replacement of the supported execution path. New application code uses the [MIT license](LICENSE); [NOTICE.md](NOTICE.md) explains original attribution and data exclusions. Optional dependencies and external datasets keep their own licenses and terms.
