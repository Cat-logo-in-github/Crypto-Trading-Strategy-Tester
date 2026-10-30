# Arbitrary inputs, model uploads and inference rules

The research workflow separates three questions: what to measure, what outcome a model should predict, and how a model output becomes a trading decision. A traffic count, urban indicator, maritime observation, weather value or a user's own numeric measurement can be an input or target. No financial relationship is assumed merely because a dataset can be joined to a market chart.

## Input features and prediction targets

Import or fetch a tabular CSV/JSON dataset, map its observation and availability timestamps, choose its fields and align it to the selected market bars. Numeric columns retain their names. The input layer can turn categorical fields into fixed hash features, so a vocabulary is not fitted on future data. Review the mapping and provenance before training; a model cannot establish whether supplied publication timestamps are truthful.

`run_tabular_model(bars, feature_rows, config, pretrained=None)` accepts one named-column dictionary per market bar. Each value must have been available by that bar's close. Missing configured inputs exclude that observation from training/inference; a missing inference does not create an order or silently liquidate the portfolio. Warmup, expiry, lag and alignment belong to the data/feature layer.

Choose up to 32 input features and a separate target field. The target can be `market.close` or any aligned external numeric column. For horizon `h`:

| Target type | Label | Built-in model |
| --- | --- | --- |
| `increase` | `1` if target at `t+h` exceeds target at `t`, otherwise `0` | Logistic regression, probability output |
| `return` | target at `t+h` / target at `t` - 1; zero denominators are unavailable | Ridge regression |
| `level` | target value at `t+h` | Ridge regression |

An external target uses the point-in-time aligned values at those two decision times. Sparse observations may therefore remain unchanged over many bars. Select a meaningful sampling interval/horizon, inspect missingness and stale-value assumptions, and avoid treating repeated carried observations as independent measurements.

The training workflow uses contiguous chronological periods. Training normalization is fitted only on training data. Labels reaching a later period are purged, and regularization is selected using validation error or log loss. The final test does not choose a model. Defaults reserve 60%/20%/20% of raw bar time; enough complete rows must remain in every period. Classification diagnostics use a fixed 0.5 classification boundary, while trading may use a different explicit threshold. There is no automatic evidence of causality or financial profitability.

## Explicit inference-to-trade policy

For example, a model can estimate the probability that an external count will rise, while the traded instrument is a completely separate market dataset:

```json
{
  "feature_names": ["traffic_count", "urban_index"],
  "target_field": "traffic_count",
  "target_type": "increase",
  "horizon": 1,
  "model_family": "logistic",
  "decision": {
    "comparison": ">",
    "threshold": 0.5,
    "when_true": {"buy_cash": 100},
    "when_false": "hold"
  }
}
```

`buy_cash` is the maximum cash budget including fees. Alternatively choose `target_weight` from zero to one. Comparisons are `>`, `>=`, `<`, `<=` or `==`; the false action is `hold` or `exit`. A probability threshold must be in `[0,1]`. Predictions are made from completed information, then the shared simulator fills the intent at the next supplied market open using configured cash constraints, fees and adverse slippage.

Each inference record includes the observed input values, output, actual future target when available, condition match, requested intent, subsequent fill/no-change status, and following market move. The discrepancy view helps identify a correct external forecast followed by an adverse market bar, missing orders because of cash limits, or costs overwhelming a small move. These diagnostics are separate from realized per-trade profit. A model can forecast its target accurately and still support a poor trading hypothesis.

## Upload a pretrained numeric JSON model

The built-in portable JSON format is numerical and does not execute uploaded Python. It supports `logistic`, `ridge` and `linear` families, plus the earlier `hypothesis-lab/ridge-v1` artifact. Example:

```json
{
  "schema": "hypothesis-lab/tabular-v1",
  "family": "logistic",
  "feature_names": ["model_count"],
  "means": [100],
  "scales": [10],
  "coefficients": [1.2],
  "intercept": -0.3,
  "trained_through": "2022-12-31T23:59:59Z"
}
```

The score is `intercept + sum(coefficient * (input - mean) / scale)`. Logistic models apply a sigmoid; linear/ridge models return the score. Scales must be positive and all numeric values finite. Map model input names to available data columns with `feature_mapping`, for example `{"model_count":"traffic_count"}`. Uploaded models reuse their own scaling; the app does not refit preprocessing or guess feature order.

An uploaded model is replayed without training or selecting parameters on the evaluation period. Set an evaluation start. A declared training end overlapping that start is rejected. Training provenance that is absent or unverifiable is prominently reported; modern or externally trained models do not acquire a valid historical out-of-sample claim merely by being replayed on past dates. `pickle`, `joblib`, Python scripts and executable model objects are not loaded by the browser workbench.

## Optional ONNX models and large local files

Install the optional runtime on the user's computer with `python -m pip install -e ".[onnx]"`. No model weights are included in the repository or installed automatically.

Upload a self-contained ONNX graph up to 5 MB, or explicitly allow the local runtime to read an existing absolute `.onnx` file path. The file-path mode limits the main graph to 2 GB; external tensor sidecars and runtime memory are the user's responsibility. Graph hashes identify the main graph, not an independently hashed bundle of every external tensor file. For larger or differently shaped models, use a user-controlled inference endpoint.

The current CPU adapter accepts one float32/float64 `[batch, features]` tensor and a selected numeric scalar output per row. Choose the input feature order, exact output name, output column for a multi-column tensor, and `probability` or `prediction` output kind. Fixed batch-size one graphs are evaluated one observation at a time. Sequence/ZipMap outputs, multiple input tensors and arbitrary sequence preprocessing require a different user-side adapter or endpoint. Numeric probability outputs outside `[0,1]` are rejected.

The local-file option runs a model chosen by the user and can consume substantial memory/CPU. It is not a general-purpose isolation boundary for hostile graphs. ONNX runtime behavior and supported operators follow the [official ONNX Runtime Python API](https://onnxruntime.ai/docs/api/python/api_summary.html). Optional-runtime verification is reported separately from base tests.

**Native ONNX execution is unverified on this local Windows host.** The optional packages could not be obtained during this run because their download host could not be resolved. Numeric JSON inference and mocked ONNX shape/hash/error contracts were executed, but those tests do not establish that a native graph executes correctly. The base suite explicitly skips two native-runtime tests when dependencies are absent. A separate Ubuntu CI job installs the optional runtime plus the graph-construction test package, requires successful imports, and executes a tiny self-contained MatMul/Add/Sigmoid graph through both upload and local-file paths. This CI job is configured; its remote result is not claimed as executed here. No pretrained weights are downloaded by these tests.

## User-controlled model and language-model endpoints

Connect an existing local inference service instead of uploading weights. The workbench supports a numeric tabular JSON contract or a compatible non-streaming chat-completion endpoint. Local HTTP is limited to loopback hosts; remote HTTPS requires explicit opt-in. Credentials are supplied through a session-only field rather than embedded in URLs. Redirects are refused so a credential cannot be automatically forwarded to another host.

The tabular contract sends selected `feature_names` and a matching two-dimensional `features` array, and reads a configured dotted response field containing one scalar per observation. The language-model contract sends the configured model name, prompt, generation budget and sampling setting to the selected service. A literal `{features}` placeholder is replaced only with the configured current historical features; future outcomes and unselected columns are not supplied.

Language-model output can be measured using a strict JSON numeric field, case-insensitive phrase presence, text length, or the endpoint's reported prompt/completion/total token count. Token counts must be reported nonnegative integer metadata; booleans, fractions, numeric strings and negative counts are rejected. Counts are never guessed when the server does not provide them. A count-based rule uses `prediction` output kind; it is not a probability. Model/version/tokenizer/sampling changes can change the measurement. The returned text display is bounded, while the text-length signal records the full received text's character length.

Prompts may also use `{target}` for the configured target field and `{horizon}` for the forecast horizon. Only their definitions are inserted, not future target values. Endpoint results calculate future target labels from the aligned dataset using the same increase/return/level conventions described above. A missing future observation is unknown, not an incorrect forecast. Classification accuracy and correct-forecast discrepancy flags require both a probability output and a known binary increase target; ordinary numeric scores receive residual diagnostics instead.

Only supported public connection settings are included in results. Credential/password/token fields are excluded, and a known session credential echoed by the model is redacted before output is retained or displayed. This does not make the selected endpoint trustworthy: the user chooses the receiving service and its own retention policy.

Historical endpoint replay is bounded to an explicit 1-64 observation budget. Actual calls occur now, not at simulated historical times. Modern language models can contain later knowledge even when their prompts contain only earlier features. `model_config.include_inference_latency` defaults to true and adds the measured present-day service duration to decision readiness, before configured order latency. Disabling it explicitly makes duration diagnostic only. This is a timing scenario, not proof of historical model/hardware availability. A small delay may skip an entire coarse bar; see the [engine audit](engine-audit-2026.md).

A language model may also suggest data-discovery terms and candidate measurements. That generated plan does not execute code or establish that a source exists, has a suitable license, or contains point-in-time history. Review the source metadata and mappings before a fetch or experiment.

Run the complete synthetic example with `python examples/generic_model.py`. It deliberately constructs a relationship to verify the pipeline and is not evidence about a real dataset or trading edge.


### Custom future conditions and own compute

Set target type **My future condition** and enter a Boolean expression over your mapped measurements, for example `col("knitting_searches") > mean(col("knitting_searches"), 7)`. The target is that condition at the configured future horizon, not a new input that reveals the future. Baseline scaling/fitting use training data; validation selects the candidate and the final held-out slice evaluates it. Slow or delayed observations define future **available measurements**, not automatically the corresponding physical event date.

A compatible tabular prediction service receives a bounded selected matrix in one request (up to 5,000 rows). LLM inference retains a separate call budget. The optional [compute service](compute-integration.md) can extract private/raw formats and train with user hardware/frameworks; no weights or SDKs are added to the default ZIP. Declared training times must precede inference. Pretraining claims and service-reported metrics remain declarations, so independent raw-data/forward validation is still needed.
