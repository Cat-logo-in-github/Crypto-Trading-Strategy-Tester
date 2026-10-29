# Your first experiment

Use Python 3.11+ and open a terminal in the extracted `hypothesis-lab` folder. Create a virtual environment with `python -m venv .venv`; activate `.venv\Scripts\activate` on Windows or `source .venv/bin/activate` on macOS/Linux. Then run:

```console
python -m pip install -e .
python -m hypothesis_lab
```

The standard-library application opens a local browser interface and binds to `127.0.0.1`. For manual browser launch or a different port, use `python -m hypothesis_lab --port 8765 --no-browser`. Stop with Ctrl+C or **Stop app**. Initial installation may obtain free build tooling; installed core workflows need no account, paid service or network connection.

## Start with a question, not a prescribed dataset

Open **Data discovery**. Describe an idea and choose **Interpret data requirements** to review proposed measurements, search terms and clarifications. The planner does not invent an exact dataset or automatically turn every sentence into a valid strategy. Search a public catalog, inspect its publisher and coverage, or import an authorized CSV/JSON export.

For a complete offline introduction, choose **Use synthetic world-signals demo** or one of the example chips. Its sales, traffic, urban-growth, shipping, weather and rubber-duck observations are generated software fixtures. They do not establish actual economic relationships or market performance.

Inspect and map observation time, publication/availability time, timezone, selected fields and expiry. Click **Validate & use these features** after changing the mapping. Missing publication information defaults to acquisition time, so a downloaded value cannot silently trigger a trade in the historical past. An explicit assumed historical lag is an exploratory scenario and is labeled accordingly.

## Try a rule or a model

In **Strategy research**, inspect the interpreted rules, fee-inclusive buy amount or target exposure, entry/exit behavior, starting cash, fees, slippage and market interval. Imported observations can be used as `event:field_name` conditions combined with market indicators through AND/OR rules. A simple supported sentence is:

```text
Buy $100 when ice_cream_sales > 120
```

Map that field first. A threshold does not mean a rise or a forecast; use an explicit causal transformation or model when that is the actual question. Unsupported sentences return a clarification error rather than guessed rules. The original temperature example and market-only templates remain available.

In **Models & inference**, choose mapped inputs and a target such as `merch_sales`, a forecast horizon and a future outcome. The core trains logistic probability or ridge numeric baselines on chronological train/validation/test periods. Choose how the output becomes a trade, for example:

```text
If probability of merch_sales increasing > 0.5:
    buy up to $100 including fees
Otherwise:
    hold the current position
```

Alternatively upload a supported numeric JSON model, use optional ONNX, or connect a model/LLM service you operate. Large weights and model SDKs are not bundled in the application ZIP. See [model inputs](model-inputs.md) for exact formats and boundaries. The older five-market-feature ridge workflow remains a separate baseline.

## Inspect what actually happened

Run the experiment and inspect the dark research terminal: OHLC candles, execution markers, time-range controls, portfolio equity/drawdown/exposure and the full paged execution blotter. Select a fill to see its decision/fill times, cash, position, fee, slippage and related inference. The inference table separates the realized external target from the following market return; the latter is not the whole trade's realized P&L.

Every supported strategy uses the same next-open, long-only spot execution path and a compatible buy-and-hold benchmark. A correct external forecast can still be an unprofitable trading hypothesis. See [methodology](backtesting-methodology.md).

## Your data and retention choices

UI runs stay in session memory by default. The session retains up to 20 recent runs, evicting older records when its estimated JSON buffer exceeds 50 MB; the latest run is retained. Use the shared **Save this experiment on this computer** checkbox only when you want persistence. In **Experiment history**, choose **Include explicitly saved local runs** to view or rerun those records after restarting. Exporting is a separate, explicit download and can include imported data or model parameters.

Explicitly saved state uses `HYPOTHESIS_LAB_HOME`, otherwise `%LOCALAPPDATA%/HypothesisLab` on Windows or `~/.local/share/hypothesis-lab` elsewhere. Source/model requests go from your computer to the provider you select; there is no app-operator backend. Optional source/model keys are session inputs. The legacy Alpha Vantage test has a separate explicit local-credential save choice. See [settings](settings.md).

## Offline command-line checks

```console
python -m hypothesis_lab sample --output sample-result.json
python -m hypothesis_lab ml --output ml-result.json
python -m unittest discover -s tests -v
```

The CLI writes research output only when you supply an output path; these commands do not automatically save run history. To launch directly from source without package installation, set `PYTHONPATH=src` (`$env:PYTHONPATH='src'` in PowerShell) before the same startup command.

For the full question-to-data-to-inference walkthrough, read [research workflow](research-workflow.md). For real-source discovery, authentication, licensing and historical-availability limits, read [data sources](data-sources.md).
