# Five unusual questions, tested as software trials

These examples are a student project's controlled historical paper-trading trials. **All alternative observations and the default market are deterministic synthetic fixtures.** The numbers describe ingestion, causality, inference and accounting behavior. They do not show that any real-world relationship works or that a strategy has an edge.

Each question has a fixed seed, threshold, sizing policy and methodology. The market generator uses a separate random stream from every observation generator. No seed, rule or model was chosen for a favorable test return. Positive, negative and abstaining outcomes are retained.

| Question | Input structure | Explicit interpretation | Decision path |
| --- | --- | --- | --- |
| Could midnight horror borrowing tell us about risk appetite? | Monthly CSV panel with Year/Month and two branches | North branch only; horror/all-loan share; recorded publication time; month end and 45-day expiry | Share above 0.35 and its 20-bar change positive; sell below 0.30 |
| Does the burnt-toaster repair mix forecast a waiting queue? | Nested NDJSON with notes and completed/failed repairs | Case-insensitive burnt-phrase count; external queue target three bars ahead | Chronological logistic baseline; buy $100 above 0.55; otherwise hold |
| Could pigeon/pizza sightings in one plaza matter? | GeoJSON Points | Explicit rectangle membership property, region filter, complete daily reporting, then daily event counts | Seven-bar average count above 3; sell below 2 |
| What does a gnome-auction model actually do? | JSON records wrapper with listing text, bids and clearance | Explicit authentic/damage phrase counts; model-input mapping | Plain numeric JSON logistic artifact; buy $100 above 0.55; otherwise exit |
| Can speedrunner resets predict knitting fever? | TSV reset/personal-best telemetry and search index | Future user-defined condition: search index above its own trailing seven-bar average at t+3 | Chronological logistic baseline; target 60% long above 0.55; otherwise exit |

The questions are intentionally odd. Their definitions are concrete enough to fail. In model examples the forecast target differs from the traded instrument, making it possible to inspect the gap between predicting external activity and earning a market return.

## Try the Strategy lab in the app

Open **Strategy lab** to inspect the five questions and definitions. Run one trial or all five, with the fixed sensitivity/negative controls enabled by default. The comparison shows actual net returns, compatible benchmarks, commissions and fill counts; each result also shows replay/prefix checks and whether prose compiled automatically or used a reviewed structured definition. **Inspect candles, fills & portfolio** opens that returned normal experiment record without rerunning it.

The same panel has an optional **Your hardware / your service** form. It can send the current mapped table, or explicit local path metadata to your loopback service. Review extraction results before applying the table; review a returned prediction connection before using it under Models & inference. No service is installed or started automatically. See [compute integration](compute-integration.md).

In the guided setup's **Period** step, an optional quote/trade replay section accepts a session-only CSV/NDJSON history with explicit instrument, quote-age and size assumptions. Actual event data must cover the same instrument/period; ordinary OHLC data cannot reconstruct it. These fixed software trials keep their own declared execution assumptions.

## Run locally

From an installed source environment:

```console
python examples/scenario_lab.py
python examples/scenario_lab.py --scenario repair_cafe --full-records --output repair-trial.json
python -m unittest discover -s tests -p test_scenarios.py -v
```

Without `--output`, the example prints a summary and writes no report. The functions do not save UI history or call a provider/model endpoint. Large model weights, paid APIs and optional runtimes are not needed.

The Python API is:

```python
from hypothesis_lab.scenarios import catalogue, scenario_payload, run_scenarios
from hypothesis_lab.research import run_experiment

questions = catalogue()
payload = scenario_payload("pigeon_pizza")
record = run_experiment(payload, persist=False)
report = run_scenarios(include_controls=True, include_records=False)
```

`catalogue()` returns fresh metadata, questions, measurement requirements, format, mode, target, seed and limitations. `scenario_payload()` supplies the actual mapping and normal algorithm/model configuration. The rule examples call the real deterministic language planner. The report records whether it compiled the prose or required the reviewed explicit expression. Model/target/upload configurations are reviewed structured definitions, not falsely labeled automatic natural-language compilation.

The gnome artifact has fixed hand-authored weights to test JSON inference and feature mapping. It is not a trained auction/financial model, and its training provenance is not asserted. The two baseline trainers fit their scaling and parameters on past data, select supported regularization on validation and reserve the final test. Split-boundary labels are purged. Rule trials use a fixed final 120-bar evaluation with earlier indicator warmup.

## Controls and audit trail

Every trial runs the actual parser, mapping, availability alignment, causal calculations, model or rule decisions, order accounting and matched-cost buy-and-hold benchmark. Reported values include return, excess return, drawdown, commission, spread/slippage impact, trade count and the actual evaluation window. Explicit full records include candles, inference decisions, orders, fills and portfolio history.

The predeclared checks are:

- Exact replay from the ordinary exported experiment configuration and inputs.
- Prefix causality: removing later bars and unpublished observations cannot change earlier signal rows.
- A fixed adverse-cost scenario: 30 bps proportional fee, 40 bps full spread, 20 bps additional slippage and $1 fixed commission. These are assumptions, not venue measurements.
- A fixed neighboring threshold, displayed without selecting whichever result looks best.
- A negative control that moves all publications beyond evaluation. Rules must produce no fills; models must reject evaluation without complete historical inputs.

No confidence interval or statistical significance is claimed. Monthly observations repeated across days do not create independent daily evidence. Overlapping target horizons and repeated searches also reduce independence.

## Replacing fixtures with real evidence

`scenario_payload()` and `run_scenarios()` accept an optional `market_csv` and require `market_provenance` identifying the authorized source, instrument, daily interval, retrieval date and usage rights. These functions never download market data automatically. Their alternative observations remain synthetic and retain their original 2022–2023 dates; the generator does not shift them to manufacture overlap with a recent market snapshot. Insufficient overlap correctly prevents a model evaluation.

To study an actual question, replace the observation fixture too, verify coverage and permissions, and document the timestamp of every historical release/revision. Real events can be missing, real auction listings can be selected, and public catalog records can measure a proxy rather than the desired quantity. A complete synthetic event log is not evidence that a real feed is complete.

Pre-register targets, horizons, thresholds, costs and the number of hypotheses tried. Keep unsuccessful experiments. Evaluate independent periods and instruments, use time-aware uncertainty estimation, and retain an untouched forward period. Forecast accuracy, a causal explanation and profitable trading remain separate claims. Daily bar opens and editable delays do not reconstruct intrabar fills or order-book liquidity.
