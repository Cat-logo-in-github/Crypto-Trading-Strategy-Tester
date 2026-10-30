# Your own extraction and training service

The optional compute adapter connects the workbench to a service you operate. That service can use your hardware, private data, preprocessing tools, frameworks and model weights. The app sends one explicit request and accepts bounded structured results. It does not install a training framework, execute generated Python, read model weights or claim that arbitrary binary inputs can be interpreted automatically.

The built-in tabular trainer remains available without a service. This adapter is for workloads whose extraction/training you implement or expose separately. It is not a cloud compute broker or an account-creation feature.

## Python entry point and transport

```python
from hypothesis_lab.compute import run_compute

connection = {
    "endpoint": "http://127.0.0.1:8767/compute",
    "allow_remote": False,
    "timeout_seconds": 60,
}
result = run_compute(connection, request, credential=None)
```

`run_compute` performs exactly one synchronous JSON POST to the endpoint as entered. It does not append a route. The request schema is `hypothesis-lab/compute-v1`. A separate credential, when supplied, becomes an Authorization Bearer header only. No credential store, telemetry, disk result file, automatic retry, job polling or service startup is provided by this module.

The service must complete within the chosen 1..120 second timeout (default 60), return at most 4 MB, and use the complete-response schema below. The request cap is 6 MB, including JSON encoding overhead; inline tables retain their own 4 MB/5,000-row limit. Long training should happen in your service's own workflow before exposing a supported bounded request. A timeout or lost connection does **not** prove that the service canceled its work. Do not retry an expensive job without checking it.

Loopback HTTP/HTTPS is allowed. `localhost` DNS is checked and pinned to loopback addresses. Remote use requires `allow_remote: true`, public HTTPS on port 443, public-address DNS validation/pinning and valid TLS. Private-network and metadata-service addresses are not remote targets. Proxy environment settings are ignored. Redirects are refused before credentials or local path metadata can be forwarded. Endpoint URLs cannot contain credentials, queries or fragments.

## Request

```json
{
  "schema": "hypothesis-lab/compute-v1",
  "operation": "train",
  "input": {
    "kind": "manifest",
    "files": [
      {
        "path": "D:\\My Research\\private-counts.parquet",
        "role": "train",
        "media_type": "application/vnd.apache.parquet",
        "description": "My authorized private measurements"
      }
    ]
  },
  "task": {
    "description": "Predict whether the future measured count exceeds its trailing average",
    "feature_names": ["count"],
    "target_type": "condition",
    "target_condition": "col(\"count\") > mean(col(\"count\"), 7)",
    "horizon": 1,
    "training_start": "2020-01-01T00:00:00Z",
    "training_end": "2022-12-31T23:59:59Z",
    "evaluation_start": "2023-01-01T00:00:00Z",
    "evaluation_end": "2023-12-31T23:59:59Z"
  },
  "options": {
    "framework": "my-service-adapter",
    "device": "my-local-device",
    "seed": 42
  }
}
```

Operations are `extract`, `train` and `evaluate`. The `options` object contains bounded finite JSON settings understood by your service; the app does not execute them. Keys containing credentials are rejected. Configure any additional service-side provider accounts separately.

`task` supports `description`, optional `feature_names`, target fields, horizon and explicit training/evaluation timestamps. `train` requires `training_end`. `evaluate` requires `evaluation_start` and `evaluation_end`. Boundaries must be timezone-aware, chronological and disjoint when both training and evaluation are declared.

For `increase`, `return` or `level`, specify `target_field`. For `condition`, specify a bounded `target_condition` expression using the documented [Signal Studio](signal-studio.md) grammar. The service evaluates that condition on the future row at `horizon`; the app validates the expression grammar and requires an exact task echo. It cannot independently prove that a remote or external trainer obeyed the task or avoided evaluation data.

### Two explicit input modes

**Local manifest:** one to 128 files, each with an absolute local `path` and `role` (`source`, `train`, `validation` or `test`). Optional fields are `media_type`, `description` and an already-known 64-character `sha256`. Paths must be distinct; relative paths, URLs and network-share paths are rejected.

The app does **not** open, inspect, hash, stat or upload these files. It sends only the selected metadata to a loopback service. The service must have access to the same filesystem or implement an explicit mapping for a container. A declared hash is not verified by the app. Do not interpret a manifest's existence as proof that a file exists or that a specialized extractor is installed.

Manifests cannot be sent to a remote service, even with `allow_remote`. Absolute local path values in remote table rows or service settings are also rejected. Remote compute must use explicitly supplied inline data and service-side model identifiers, not a blind local-file upload.

**Inline table:**

```json
{
  "kind": "table",
  "content": "observed_at,available_at,count\n2024-01-01T00:00:00Z,2024-01-01T01:00:00Z,12\n",
  "format": "csv",
  "mapping": {"field_columns": ["count"]}
}
```

Supported inline formats are CSV, TSV, JSON records, NDJSON and GeoJSON properties/Point coordinates, within the existing parser bounds. Sending a table is an explicit transmission of its contents to the selected service. Review privacy and usage rights before choosing a remote service.

Parquet, spreadsheets, archives, images, audio, video, raster/NetCDF/HDF, proprietary files and arbitrary framework checkpoints are **not** read by the app. A local manifest can refer to them only because your service performs the required extraction. Media-type metadata is a description, not a capability promise.

## Completed response

All responses require `schema`, `status: "complete"`, matching `operation`, and an exact echo of the normalized `task` received in the request. Other permitted top-level fields are `dataset`, `prediction`, `evaluation`, bounded `provenance` and text `warnings`. Executable artifacts, code and arbitrary opaque model blobs are not response formats.

### Extraction result

```json
{
  "records": [
    {
      "observed_at": "2024-01-01T00:00:00Z",
      "available_at": "2024-01-01T01:00:00Z",
      "count": 12,
      "event_label": "NY"
    }
  ],
  "mapping": {"field_columns": ["count"], "max_age_hours": 48},
  "provenance": {"description": "Documented service extraction; publisher timestamps retained"}
}
```

Put this object in `dataset`; extraction requires it, while training/evaluation may include it. It must contain 1..5,000 bounded records with timezone-aware `observed_at`. Missing `available_at` becomes acquisition time with a warning; supplied availability must not predate observation. The app never invents historical publication times. Canonical outputs cannot override availability with a lag. Selected fields are inspected using the existing quality/mapping workflow.

The adapter returns `dataset.content`, `format: "json"`, `records`, normalized `mapping`, `inspection`, provenance and warnings. These can be reviewed and then used as ordinary feature data. A text-only extraction can remain a table until the user explicitly defines numeric text/category signals.

### Training result and prediction reuse

Training requires `prediction`:

```json
{
  "connection": {
    "kind": "tabular",
    "endpoint": "http://127.0.0.1:8767/predict",
    "output_field": "predictions",
    "output_kind": "probability",
    "max_calls": 12
  },
  "feature_names": ["count"],
  "trained_through": "2022-12-31T23:59:59Z"
}
```

The prediction endpoint must share the explicitly selected compute service's origin. A different host/port is a separate connection choice. Output kind is probability for `increase`/`condition`, numeric prediction for `return`/`level`. Feature names/order must match a requested order when supplied. `trained_through` must not exceed the declared training end or overlap evaluation.

The service owns weights, framework, feature extraction and prediction lifetime. No model weight/artifact is downloaded by this adapter. The normalized result exposes `prediction_connection`, `model_config` and declared `training_provenance`. After review, these can configure the existing `mode: "endpoint"` workflow; supply a fresh session credential separately. That numeric prediction route sends `feature_names` plus a two-dimensional `features` array and expects a matching numeric prediction list. Models requiring raw images/sequences need your service to extract compatible named features first, rather than silently changing the endpoint contract.

### Evaluation result

Evaluation requires `evaluation: {metrics, rows, start, end}`. `metrics` contains 1..32 names with finite numbers or null; booleans, numeric strings and executable/text metric values are rejected. `rows` is a positive bounded integer. `start` and `end` are timezone-aware, ordered and contained within requested evaluation bounds. These are clearly labeled **service-reported metrics**, not independently recomputed results or evidence of a financial edge.

## Privacy, provenance and scientific limits

Known session credentials, common secret fields and selected manifest paths are removed/redacted from normalized results. Input summaries contain counts/format rather than manifest paths. The module performs no persistence; only explicit app save/export can retain a normalized result. Your selected service can read the authorized paths and may retain data, models or logs under its own policy. Localhost alone is not a guarantee about what that service does afterward.

The response records a request fingerprint, acquisition time and measured wall time. These do not verify private source authenticity, training data vintage, reproducibility of external hardware, truthful metrics or absence of evaluation leakage. A declared historical training cutoff is an attestation. Retain your own reproducible service configuration and independent evaluation evidence.

Measured extraction/training wall time is diagnostic. The reusable prediction route follows the workbench's separate inference-latency replay setting and [execution conventions](engine-audit-2026.md). Completing a training request does not run a backtest, publish a model, issue a brokerage order or prove that the extracted feature predicts the market.
