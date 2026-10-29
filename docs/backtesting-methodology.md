# Backtesting methodology and metric conventions

## Information and execution timing

A market `Bar.timestamp` is the interval's **open** time. Its OHLC values are available to a strategy only after the completed interval, at `timestamp + bar_seconds`. The interval is explicitly configured. A decision based on completed bar i is filled at bar i+1's open. A final-bar decision expires because there is no subsequent executable bar. Gaps are not silently filled; the next available open may be later than one interval.

External events have distinct observation and availability timestamps. At a decision time, only revisions with availability no later than that time are eligible. Among those, the newest observation and its latest available revision are used, subject to a configured age limit. Revised reanalysis with an assumed publication lag is still not a true point-in-time dataset.

## Supported execution and accounting

The engine supports one spot instrument, fractional units, cash and long-only exposure. Fees are proportional to actual filled notional. Buys pay an adversely increased open and sells receive an adversely reduced open. A `buy_cash` budget includes both notional and fees and is clipped to available cash. A target weight lies in [0,1] and is solved using post-cost equity marked at the open, with no borrowing or shorting.

Cash changes only by filled notional and fees. Average cost basis includes buy fees; partial sales allocate basis proportionally. Realized sale P&L includes sale costs. Equity is cash plus units marked to each completed close. Final holdings are marked, not liquidated, so an eventual liquidation would incur further costs. No order-book depth, spread beyond configured slippage, partial fill, volume participation, latency, dividends, splits, funding, tax or exchange-calendar model is supplied.

## Benchmarks and reported metrics

Buy-and-hold submits its first intent after the first completed bar and uses the same next-open execution, initial cash, period and configured costs as the candidate. For strategies with feature warmup, the benchmark's earlier exposure is deliberate and visible. Do not compare different periods or capital as though they were compatible.

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
