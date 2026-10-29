# Research from an unusual question

The workbench connects a question, observations, a precise signal, simulated orders and an inspectable result. Temperature is one example. Sales, traffic counts, shipping activity, urban indicators, categorical observations, defined text measurements and outputs from your own model can use the same pipeline.

A question still needs a measurable quantity, sufficient overlapping history and permission to use the data. A public catalog cannot guarantee an exact dataset for every idea. The app makes that gap visible instead of silently replacing the question with an unrelated proxy.

## 1. Define what the question measures

Open **Data discovery** and describe the idea. **Interpret data requirements** proposes search terms, measurement requirements, signal definitions and questions that need clarification. Review the proposal before using it. It is not an unrestricted natural-language strategy compiler.

For example, "buy when my merch sales rise" needs decisions about:

- Which shop, product group and sales measure: units, orders, revenue or another quantity.
- What "rise" means: a change over one day, a trailing week or a future prediction.
- When the observation was published or became available.
- Which market instrument to trade, how much to buy and when to exit.

Private store sales generally require the owner's authorized export or documented API. An ice-cream vendor permit count, shop location list or retail inspection dataset is a different measurement from ice-cream sales. The app does not assert that a catalog match is an exact answer.

The optional LLM planning choice uses the model connection configured under **Models & inference**. Its output is a candidate plan to inspect; it cannot create a dataset, establish publication history or prove a predictive relationship.

## 2. Find or import the observations

Use one of these paths in **Data discovery**:

- Search the public city/government catalog or World Bank indicators. Read the returned description, publisher page, access conditions, units and coverage before fetching a candidate.
- Choose a local CSV or JSON file. JSON may be an array of records or a supported `records`, `data` or `items` wrapper. Small nested objects and short arrays are flattened into named fields.
- Configure a documented HTTPS CSV/JSON endpoint under **Fetch a known HTTPS API / other connector**. Select the response format, a JSON record-array path when needed and the provider's documented authentication header. Supply your own session key only when required.
- Use the **synthetic world-signals demo** to learn the workflow without an account or network request. Its ice-cream, merch, traffic, urban-growth, shipping, weather and rubber-duck columns are generated fixtures, not actual economic observations.

The IMF PortWatch connector is one concrete no-key example for daily aggregate maritime activity. It does not represent live vessel positions or guarantee historical publication timestamps. See [data sources](data-sources.md) for source coverage, access and licensing limits.

The downloaded preview may be bounded to a subset of a larger dataset. Check that it contains enough relevant rows and a useful historical period. Annual city indicators, hourly traffic sensors and daily prices need explicit decisions about time alignment and expiry; they are not interchangeable frequencies.

## 3. Map time and feature fields

Inspect the preview, then configure:

- **Observation time:** what period the measurement describes.
- **Publication / available time:** when a hypothetical strategy was allowed to know it.
- **Missing timezone assumption:** choose an explicit interpretation for date-only or naive timestamps, or supply timestamps with their own timezone.
- **Expiry:** how long an observation remains usable. Expired or missing observations do not satisfy a condition or silently become zero.
- **Numeric and categorical fields:** choose the quantities the experiment may use.

When a real publication column exists, use it. When it does not, the conservative default is acquisition time. That prevents a value fetched today from generating historical orders years ago. You may instead select an explicit assumed historical publication lag for an exploratory scenario. The result warns that the lag is an assumption, not verified point-in-time evidence.

Numeric columns work directly. JSON booleans can be numeric inputs; CSV booleans can be represented explicitly as 0/1. Categorical fields use fixed hash buckets rather than a vocabulary learned from future data; collisions are possible. Text can be converted into an explicit phrase count, phrase-presence indicator or character length through advanced mapping. Raw images, audio and arbitrary nested documents require user-defined preprocessing or a compatible local inference service.

Click **Validate & use these features** after editing the mapping. The application joins observations to market decision times using availability and expiry. Future publications and later revisions are not exposed early.

For a simple observed-feature rule, select a mapped `event:field_name` in the condition builder, such as `event:ice_cream_sales > 120`. AND/OR conditions, technical market indicators and position sizing remain explicit. A "rise" rule needs a defined transformation; a raw threshold is not automatically interpreted as growth.

## 4. Train or connect a model

Open **Models & inference**. Market OHLCV, bar duration, fees, slippage and starting capital still come from **Strategy research**. The input observation dataset comes from **Data discovery**. These are separate datasets and can describe different phenomena.

### Train a local baseline

Choose input columns, a target quantity and a future outcome:

- **Probability of an increase:** a logistic model predicts whether the configured future target exceeds its current value.
- **Relative change:** a ridge model predicts the configured target's proportional change.
- **Future numeric level:** a ridge model predicts its future level.

The forecast horizon is measured in market bars. Target values come from the aligned measurement series; inspect its publication lag and frequency before interpreting what a one-bar forecast means.

Training and validation fractions are chronological. Scaling is fitted on training only. Labels crossing a later split boundary are purged. Validation selects supported regularization settings; the final test period is used for evaluation. A larger range of arbitrary input fields does not remove leakage, selection-bias or sample-size concerns.

Optional transformations are causal operations with a named source and output: lag, difference, proportional change, trailing mean/sum or z-score. They do not evaluate Python expressions. Ensure the model's selected input names match the features you actually intend to test.

### Upload a pretrained model

Choose **Use pretrained JSON / optional ONNX**, upload and inspect a supported artifact, and map its input names to the local dataset columns. Plain numeric JSON linear/logistic artifacts work without a heavy runtime. ONNX requires the optional local runtime and its supported input/output contract. Configure output name/column where needed. Pickle, joblib and arbitrary Python model files are not executed.

For a large ONNX graph, the optional local-path workflow reads the user's explicitly chosen local model and external weights. It does not copy those weights into the application ZIP. The original model files are needed again when rerunning a path-based experiment.

Declare the trained-through date when known and choose a subsequent evaluation period. An uploaded model with unknown provenance is flagged; uploading it is not evidence that its training data predates the historical test. See [model inputs](model-inputs.md) for exact supported schemas and model boundaries.

### Use your own model or LLM service

Choose **My local model / LLM endpoint** and configure a service you operate. A localhost endpoint is the default. The application does not bundle model weights, install an LLM for you or require a paid model provider.

An OpenAI-compatible chat service can return a strict JSON numeric field. Explicit alternatives include a text match, text length or provider-reported token count. The token-count choices require the provider to report the chosen count; the app does not estimate it silently. A tabular prediction service uses the documented matrix-to-predictions contract shown in the interface.

Choose request and output-token budgets before running. Local inference still costs time and memory. A remote HTTPS provider requires an explicit opt-in and may receive the selected query/features and charge for requests. Your credential is supplied separately and is not exported as an experiment key.

Historical LLM inference is a replay performed now. A modern model may already know later facts. Passing it historical inputs is not proof of a valid historical out-of-sample experiment.

## 5. Explain inference-to-trade behavior

Configure the comparison, threshold, action and false-condition behavior. For example:

```text
Target: shipping_volume
Outcome: probability of an increase over the next market bar
Condition: model output > 0.5
When true: buy up to $100, including fees
When false: hold the current position
```

The same structure applies to traffic, authorized sales or another supported measurement. A probability threshold has meaning only when the output is a probability. A numeric level, token count or text length needs a threshold in that output's own units.

"Buy a cash amount each signal" accumulates on each qualifying decision subject to cash limits. "Target long exposure" requests a portfolio weight and can create no new fill when that target is already satisfied. "Hold" and "exit to cash" are distinct false-condition choices.

All model intents use the same next-open execution and accounting as rule strategies. Models cannot create their own fills. Fees, adverse slippage, missing observations and available cash can change what a signal accomplishes.

## 6. Inspect the market, portfolio and discrepancies

After a run, the dark research terminal provides:

- Market candles with actual simulated buy/sell markers, time-range controls and zoom.
- A portfolio inspector at the selected bar, with cash, units, position value, realized/unrealized P&L and drawdown when available.
- Equity, drawdown and exposure views.
- An execution blotter containing all fills, filtered and paged; selecting a fill reveals its decision/fill times, fees, slippage, cash change and related model output.
- An inference-to-decision-to-execution table. Large histories can be bounded in the visible table; an explicit export includes the full record.

A correct forecast about external activity can coexist with a losing market trade. Inspect the realized target separately from the following market return, then inspect costs, timing, missing-data coverage and the economic hypothesis. The next-bar discrepancy indicator is descriptive; it is not the full trade's realized return or evidence of causality.

Compare only runs using compatible instruments, periods, starting capital, data and execution conventions. Repeatedly selecting a successful strategy on the same validation history can overfit it, even when every backtest is mechanically correct.

## Session privacy and reproducibility

The main application runs on localhost. There is no app-operator account, research backend or telemetry service. Data-source requests originate from the user's computer and go to the selected provider. A separately selected model endpoint receives the requested inputs according to its own configuration.

New UI runs are session-memory records by default. Source and model credentials are session inputs, not experiment exports. Explicitly saving a run locally can retain its imported data, configuration and results on the user's disk. Exports are user-initiated files and can contain research data or model parameters; share them only when permitted. The separate optional credential-storage UI explains its explicit local-save choice.

Session-only records disappear when the application process exits. A reproducible rerun needs the same observations, configuration, model artifact or local model/service, and relevant runtime. Remote services and revised datasets can change; exported metadata does not make an unavailable service or omitted model weights reproducible.

Read [backtesting methodology](backtesting-methodology.md), [data sources](data-sources.md) and [model inputs](model-inputs.md) before drawing conclusions from a result.
