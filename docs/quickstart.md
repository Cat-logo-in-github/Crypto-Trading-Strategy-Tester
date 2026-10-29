# Your first paper experiment

Hypothesis Lab is a student project for historical paper-trading research. It does not place real orders.

## Windows app

1. Download `Hypothesis-Lab-Windows.zip` from the repository's Releases page.
2. Extract the whole folder.
3. Open **Hypothesis Lab.exe**. Keep the extracted files together.

The portable runtime is included. No Python installation or terminal is needed. The app opens your local browser; choose **Stop app** when finished. Release downloads become available after the repository owner publishes the corresponding assets.

## Follow the five steps

Start in **New experiment**:

1. **Idea:** write a measurable question or choose **A simple market trend** for an offline introduction. An optional model can propose a draft; review it before use.
2. **Data:** keep the synthetic market sample, import completed-bar prices, and optionally add observations from a local table or **Find & prepare data**. Samples demonstrate the software; they are not actual market evidence.
3. **Signal:** build a condition, combine safe calculations in an algorithm, or choose a model output. Set the buy amount or target weight and explicit sell behavior. Preview the decision logic.
4. **Period:** choose all history, a final number of bars or dates. Set capital, fees, spread, slippage and delays. Documented fee presets are snapshots; spread and latency values remain editable assumptions.
5. **Run:** review the configuration, then choose **Run paper experiment**.

The simple market-trend example compares closing price with its trailing average. For external data, review detected dates and measurement fields before relying on a result. Separate year/month/day columns, date formats, entity filters and optional event aggregation have explicit controls. Suggested mappings are proposals you apply, not hidden changes.

Missing publication information defaults to acquisition time. A downloaded value cannot silently trigger a historical trade before it was known. You may choose an explicit historical-lag assumption for an exploratory scenario; the result flags that limitation.

## Models and other inputs

**Models & inference** supports small local logistic/ridge baselines, supported numeric JSON artifacts, optional ONNX and a service you operate. Choose the target, horizon and how the output becomes a trade. A probability threshold has different units from a future numeric value or token count.

Large model weights and SDKs are separate user installs. The application does not bundle an LLM or heavy model runtime. A remote service receives selected inputs only after your explicit opt-in. See [model inputs](model-inputs.md).

**Find & prepare data** searches public catalogs and accepts authorized CSV, TSV, JSON, NDJSON and point GeoJSON inputs. A source result can be related rather than exact, or metadata only. Private sales usually require the owner's data/API. Text measurements and causal transformations remain explicit. See [data sources](data-sources.md).

## Inspect the result

Use the dark market terminal to inspect candles, fill markers, zoom/range controls, equity, drawdown and exposure. The full execution blotter is paged and searchable. Select a fill to inspect the readiness clock, actual fill, commission, spread, slippage, cash and resulting position.

Fills use supplied bar opens. Even a small delay can move a daily-bar trade to the following day; use finer bars for latency-sensitive research. Presets do not reconstruct intrabar or order-book execution. Models trained in the app trade only in the final held-out part of the selected period.

A correct external forecast can still be an unprofitable trading hypothesis. Condition outputs are not forecast probabilities. Read the [methodology](backtesting-methodology.md) and [research workflow](research-workflow.md).

## Saving and privacy

Runs stay in session memory by default, up to 20 recent records subject to a 50 MB estimated buffer. Choose **Keep this experiment on this computer** only when you want persistence. In **My experiments**, use **Include explicitly saved local runs** to load those records after restarting. Export is a separate explicit download and can include imported data or model parameters.

Requests go from your computer to the provider you choose. There is no app-operator research backend. Source/model keys are session inputs; the legacy Alpha Vantage connection has a separate explicit local-key save choice. See [settings](settings.md).

## Source setup for developers and other platforms

Use Python 3.11+ in the extracted source folder:

```console
python -m venv .venv
python -m pip install -e .
python -m hypothesis_lab
```

Activate the environment before installing/running: `.venv\Scripts\activate` on Windows, or `source .venv/bin/activate` on macOS/Linux. For manual launch, use `python -m hypothesis_lab --port 8765 --no-browser`. The app binds to `127.0.0.1`.

Core workflows use the standard library. Installation may obtain free build tooling; installed offline workflows need no account or network. Command-line checks are:

```console
python -m hypothesis_lab sample --output sample-result.json
python -m hypothesis_lab ml --output ml-result.json
python -m unittest discover -s tests -v
```

CLI output is written only when an output path is supplied; those commands do not automatically save UI history.
