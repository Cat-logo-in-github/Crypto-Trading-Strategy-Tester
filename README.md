# Hypothesis Lab

A free, local-first research workbench for unusual financial questions. Find or import observations, define a rule, train a small model or bring your own, then inspect the simulated market trades and portfolio. No account, subscription, app-operated backend or mandatory AI service.

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

- **Discover or import data.** Search public city/government catalogs or World Bank indicators, fetch a documented HTTPS CSV/JSON API, or import your own authorized export. No-key connectors fetch directly; authenticated sources use your own session key. PortWatch maritime aggregates are one example, not the platform's only data theme.
- **Make the signal precise.** Use mapped numeric, categorical or defined text features, causal lag/rolling transformations, AND/OR rules and explicit publication/availability times. Private shop sales need the owner's data; a permit or venue count is a different proxy.
- **Train or bring a model.** Core CPU logistic/ridge baselines accept arbitrary supported named inputs and targets with chronological evaluation. Upload a numeric JSON model, use optional ONNX, or connect a model/LLM service you operate. Define the exact inference-to-trade condition, including a probability threshold or a reported LLM token-count signal.
- **Inspect the market.** Candles, buy/sell markers, zoom and time ranges connect to cash, positions, equity, drawdown, fees and slippage. The full paged blotter and inference-to-decision table help explain why an accurate external forecast can still support an unprofitable trade.
- **Choose what to retain.** Runs stay in RAM by default. Explicit local saving and exports are optional. Source/model requests originate on your computer; no app-operator backend receives the data or keys.

Try the labeled synthetic examples: ice-cream sales, a merch drop, traffic, urban growth, shipping, rubber ducks and moon phases. These teach the workflow; they are not actual economic observations or evidence of a trading edge. A testable question still needs relevant, authorized data and enough overlapping history. Catalog search does not guarantee an exact source for every idea.

## Optional models and connections

Large model weights, SDKs and heavy ML runtimes are **not** included in the small source ZIP or silently downloaded. The portable Windows runtime is a separate distribution from that source archive. Users install optional ONNX support or operate their own model service as needed; a local ONNX path can refer to their existing model files. Unsupported framework or multimodal models need compatible preprocessing or an inference endpoint.

Localhost is the model-endpoint default. A remote HTTPS provider requires an explicit choice, receives the selected inputs and may charge the user. Historical LLM replay can contain future knowledge and is not verified out-of-sample history. Token signals require provider-reported counts; they are not estimated silently.

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
- [GitHub Pages, CI and packaging](docs/releasing.md), [audit](AUDIT.md) and [verified implementation status](IMPLEMENTATION_STATUS.md)

Build the public documentation and small source release with:

```console
python scripts/build_site.py
python scripts/package.py
```

These produce `dist/site/` and `dist/hypothesis-lab.zip`; the latter excludes keys, user datasets/state, environments, caches, Git history and model weights. Source release budgets are 20 MB per ZIP and 10 MB per included file. The Windows application is a separate portable-runtime artifact, published under the stable download name above.

For GitHub Pages, push the source and choose **Settings > Pages > Source > GitHub Actions**. Pages is the documentation/download hub; research executes locally. Publishing a Pages build does not automatically create a downloadable Windows release asset.

## Scope and attribution

Execution is one long-only spot instrument with fractional next-open fills, explicit costs and cash constraints. There is no real-money execution, order-book/liquidity model, margin, corporate-action or tax model. Final holdings are marked at the last close rather than forcibly liquidated. Repeated selection can overfit historical results; prediction accuracy does not establish profitability.

The original Bitcoin Trading Bot and Research Wing source is preserved under [`legacy/`](legacy/). [AUDIT.md](AUDIT.md) explains the evidence-based replacement of the supported execution path. New application code uses the [MIT license](LICENSE); [NOTICE.md](NOTICE.md) explains original attribution and data exclusions. Optional dependencies and external datasets keep their own licenses and terms.
