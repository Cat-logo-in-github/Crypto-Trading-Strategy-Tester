# Supervised research

For the general **Models & inference** workspace introduced in version 0.2, see [model inputs and inference](model-inputs.md). It supports arbitrary mapped inputs/targets, small logistic or ridge baselines, pretrained numeric JSON, optional ONNX and the user's own model/LLM service. The market ridge baseline described below remains a separate supported workflow.

This release implements one complete CPU-only model family: ridge regression. It
uses Python's standard library, requires no account, runs offline, and saves a
numeric JSON model. Optional scikit-learn installation is an extension route;
tree models, classifiers, neural networks, and sequence models are not exposed
as working features in this release.

## Inputs and target

`hypothesis_lab.ml.run_ml(bars, configuration)` accepts validated chronological
`Bar` objects. Up to 20,000 bars and five inputs are supported in the baseline.
For each decision at bar close `t`, available features are:

| Name | Definition |
| --- | --- |
| `return_1` | `close[t] / close[t-1] - 1` |
| `momentum_5` | `close[t] / close[t-5] - 1` |
| `sma_gap_10` | `close[t] / mean(close[t-9:t+1]) - 1` |
| `volatility_5` | Population standard deviation of the last five one-bar returns |
| `volume_change` | Last volume divided by previous volume minus one; zero when previous volume is zero |

The label is `close[t+horizon] / close[t] - 1`. The horizon is one to thirty
bars. These are forecast returns, not an execution price assumption. The trading
simulation uses the common engine's next-open fills, fees, and slippage.

## Chronological protocol

The default row allocation is 60% training, 20% validation, and the remaining 20%
test, after the ten-bar feature warmup and removal of rows without future labels.
Before fitting, a horizon-sized gap is purged from the end of training and
validation: every label must end strictly before the next period's first
feature timestamp. All rolling features use only information at or before the
decision. A validation or test feature may use preceding history; that history
was already available when making the prediction.

Means and scales are estimated on training inputs only. Constant columns have a
scale of one. Coefficients fit a centered, standardized linear model with an
unpenalized intercept and a positive L2 penalty. The default alpha candidates
are `0.1`, `1.0`, and `10.0`; minimum validation mean squared error selects the
model, with candidate order breaking ties. The selected model remains fitted
only on the training rows. It is not silently refitted using validation or test
data. The final test period is evaluated once after selection.

The seed is recorded for provenance; ridge fitting and selection are
deterministic and use no random sampling. A repeated search against one
validation period can still overfit. Keep additional future data for a fresh
evaluation and record every attempted configuration.

## Configuration and inference

```python
from hypothesis_lab.ml import predict, run_ml, trailing_features

result = run_ml(bars, {
    "feature_names": ["return_1", "momentum_5", "sma_gap_10"],
    "horizon": 1,
    "train_fraction": 0.6,
    "validation_fraction": 0.2,
    "ridge_alphas": [0.1, 1.0, 10.0],
    "threshold": 0.0,
    "seed": 42,
    "initial_cash": 10000,
    "fee_bps": 10,
    "slippage_bps": 5,
})
next_prediction = predict(result["model"], trailing_features(bars, len(bars) - 1))
```

Predictions greater than `threshold` request a 100% long target; other
predictions request cash. Orders cannot execute at the close used to create
their inputs. Only test-period predictions enter the reported trading
simulation. A buy-and-hold benchmark uses the identical test bars, initial
capital, next-open convention, fees, and slippage. The final horizon bars have
no new ML decisions because their labels would be unavailable, and the last
position is marked to market.

Model data contains a schema identifier, feature names, training means/scales,
coefficients, intercept, selected alpha, horizon, seed, and training endpoint.
Use `json.dump(..., allow_nan=False)` to save the model and `json.load` followed
by `predict` to use it. Inference validates the schema and finite numeric
parameters. No pickle, joblib, or executable Python is loaded. Importing a
third-party Python strategy remains trusted local code execution and is a
separate developer workflow.

## Diagnostics and limits

Results include training/validation/test boundaries, purged-row counts, all
validation trials, test predictions and realized labels, MSE, MAE, R-squared
(null for a constant target), directional accuracy, a training-mean forecast
baseline, residual and prediction summaries, and standardized coefficients.
Coefficients are descriptive, not proof of causality. Directional accuracy is
not a significance test. Overlapping horizon labels are correlated.

Prediction error and investment return answer different questions. A positive
forecast can still lose money after trading costs. The feature set is limited,
the model is linear, the example is synthetic, and no predictive edge or
institutional quality is claimed. Multi-asset portfolios, automatic feature
search, calibrated classification, walk-forward refitting, GPU training,
hyperparameter selection on trading performance, and deep-learning families
remain future work.

Memory is proportional to the number of bars and five features. At the
20,000-bar cap, normal personal-computer CPUs are sufficient; no GPU or model
download is needed. This cap bounds the baseline rather than promising a
specific runtime on every machine.
