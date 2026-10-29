# Read-only data snapshots and forward research

Historical backtests consume fixed validated datasets. Optional provider requests fetch new observations through a separate read-only path. They never submit real orders or access a brokerage account. Core research remains available when a provider is offline.

The Kraken connector is a manually refreshed public OHLC snapshot. It exposes the last completed interval, not a guaranteed exchange tick stream. The provider returns at most 720 recent intervals and always includes a current uncommitted interval; the connector excludes that final entry. The interface should be read using both the request time and market timestamp. A successful connection does not establish absence of exchange delay, complete historical coverage or unrestricted data rights. See [official OHLC semantics](https://docs.kraken.com/api-reference/market-data/get-ohlc-data).

Alpha Vantage's optional credential test is **end-of-day quote data** on the standard plan, not a live signal. Real-time or 15-minute delayed US data requires a corresponding premium entitlement. The standard plan normally allows 25 calls/day; each connection test consumes a request. [Provider documentation](https://www.alphavantage.co/documentation/#latestprice), [quota support](https://www.alphavantage.co/support/).

Open-Meteo archive access is historical reanalysis. It is neither a live weather feed nor proof of the information published at a past trading time. A chosen availability lag is an explicit assumption and cannot reverse revisions in the underlying history.

Provider failures are reported as unavailable/error state rather than relabeled as simulated live data. Bundled data is always labeled synthetic. Missing observations, stale event values and gaps need inspection before interpreting an experiment. Do not use automatic rapid refresh: providers enforce quotas and service availability is not guaranteed.

A persistent forward paper portfolio, stateful signal/prediction history over arriving data, automatic polling/reconnection, benchmark tracking across sessions and live-log export are **planned**. Current snapshots can be inspected/imported for research; they do not constitute a complete forward paper-trading product. The historical portfolio output is a simulation, not a live brokerage balance.
