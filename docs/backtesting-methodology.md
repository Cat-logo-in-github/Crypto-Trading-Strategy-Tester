# Backtesting methodology and metric conventions

## Information and execution timing

A market `Bar.timestamp` is the interval's **open** time. Its OHLC values are available after `timestamp + bar_seconds + data_delay_ms/1000`. The interval is explicitly configured. A decision's readiness is the later of that time and an optional `Decision.available_at`; `latency_ms` then delays eligibility. It fills at the first supplied later bar open at or after eligibility. With zero delay this is the next open. Intents without a remaining eligible open expire without a fee. Gaps are retained.

This is a bar-resolution model. On daily bars, even a positive 10 ms delay after a daily boundary can skip that open and defer execution by a whole bar. The engine changes the fill price and portfolio timing; it does not reconstruct intrabar quotes or millisecond market execution. Use finer observations when that distinction matters. Pending intents are queued; there is no automatic cancel/replace or supersession policy.

External events have distinct observation and availability timestamps. Only revisions published by the decision's information clock are eligible; publications arriving during the configured data-processing delay may therefore be used. Among them, the newest observation and its latest available revision are selected, subject to expiry. An explicit missing revision remains missing. Unknown publication times default to acquisition time. An assumed historical lag is exploratory, not evidence of historical vintages.

Endpoint replay adds the present-day measured request wall time to readiness by default (`model_config.include_inference_latency: true`), then applies configured order latency. Setting it false is an explicit zero-inference-delay scenario. This measurement describes the current model/service/network, not historical hardware, model knowledge or deployment latency.

## Research periods and warmup

The workbench accepts UTC `period.start`, `period.end` and/or `period.last_bars`. A date-only end includes that entire day; only bars completing by the boundary are eligible. The selected active period contains 2..5,000 bars. Up to 1,000 preceding bars remain available for causal feature warmup, without spending active-period capital or generating prior trades. Missing warmup stays missing.

Low-level `backtest` and `benchmark` accept inclusive `start_index` and exclusive `end_index`. Pass the same bounds to `decisions_for`, so one-shot rules begin their active state in the intended window. Model training/validation/test partitions are separate from these trading bounds; trained-model performance is evaluated in the held-out subperiod, not over all selected training bars.

## Supported execution and accounting

The engine supports one spot instrument, fractional units, cash and long-only exposure. `fee_bps` charges proportional commission on actual filled notional; `fixed_fee` adds quote-currency commission per successful fill. `spread_bps` is an assumed full spread, half applied adversely per side, plus separate `slippage_bps`. A buy fills at `open * (1 + spread_bps/20000 + slippage_bps/10000)` and a sell uses the corresponding subtraction. An OHLC open is a reference trade price, so this spread construction is an assumption rather than an observed executable quote.

A `buy_cash` budget includes notional and both commission types and is clipped to cash. Target weight lies in [0,1] and is solved using post-cost equity marked at the fill open, without borrowing or shorting. Rejected, expired and unchanged intents pay no fee. Costs already affect cash/fill prices; do not subtract their reported breakdown a second time.

Cash changes only by filled notional and fees. Average cost basis includes buy fees; partial sales allocate basis proportionally. Realized sale P&L includes sale costs. Equity is cash plus units marked to each completed close. Final holdings are marked, not liquidated, so eventual liquidation would incur further costs. Order-book depth, partial fills, volume participation, queue priority, venue lot/minimum rules, dividends, splits, funding, tax and exchange calendars remain outside the model.

Named cost profiles are dated, editable scenarios, with official fee evidence separated from assumed spread/slippage/delays. They do not fetch account-specific fees, model passive maker fills or establish historically applicable rates. See the [current engine audit](engine-audit-2026.md) for source evidence, tested accounting and remaining limits.

## Benchmarks and reported metrics

Buy-and-hold submits its first intent after the first active completed bar and uses the same active bounds, initial cash, configured costs and data/order delay convention. Candidate feature warmup or per-inference readiness can still produce later exposure; those differences remain visible. Do not compare different periods or capital as though they were compatible.

| Metric | Convention |
| --- | --- |
| Total return | Final marked equity divided by original initial cash, minus one; entry costs are retained. |
| Annualized return | Calendar-duration compounded return, only reported for a period at least one calendar year; otherwise null. |
| Maximum drawdown | Most negative equity/previous peak minus one, including initial cash in the peak baseline. |
| Annualized volatility | Sample standard deviation of close-to-close portfolio returns times square root of configured periods per year. |
| Sharpe | Mean period return divided by its sample standard deviation, annualized; zero risk-free rate; null if undefined. |
| Turnover | Sum of both buy and sell filled notional divided by initial cash, not one-way or average-equity turnover. |
| Trade count | Number of fills, including buys and partial sells. |
| Closed trade count | Number of sale fills with allocated cost basis, not a reconstructed round-trip count. |
| Profit factor | Sum positive net realized sale P&L divided by absolute negative net realized sale P&L; null when there are no losses. |
| Fees paid | Actual sum of per-fill fee charges. |

Use 365 periods/year for daily crypto, or the actual annual observation count for another interval/market. A daily default applied to minute data is wrong. Annualized volatility and Sharpe are frequency-sensitive summaries; irregular/missing intervals require cautious interpretation. JSON null indicates an undefined or deliberately unavailable metric, not zero performance.

## Validation boundaries

Offline tests use deterministic small fixtures and hand-calculated cash/cost/timing cases. The weather example tests publication availability and SMA warmup. ML fits transforms on training data, selects candidates on validation data and keeps the final test period separate; see [ML methodology](ml-research.md). Fixed configurations and seeds reproduce experiment content.

The tool does not correct survivorship bias or corporate actions in user data. Repeated tests, feature searches and manual strategy selection can still overfit. A held-out period loses its independence once you tune in response to it. Correlation, fitted predictions, training rewards and attractive equity curves do not establish causality or a reliable trading edge.

See [Signal Studio](signal-studio.md) for reviewed expressions, feature interpretations and the end-to-end workflow.
