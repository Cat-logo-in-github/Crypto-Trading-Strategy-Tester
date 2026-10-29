# Datasets, providers and availability

Version 0.2 adds a general **Data discovery** workspace: public catalog search, your own CSV/JSON or HTTPS API, nested field mapping, explicit ISO/Unix time formats, numeric/categorical/text signals, and optional mapping to actual OHLCV market data. Start with [general data discovery](data-sources.md). The weather/provider contracts below remain supported examples. The interactive research runner caps market history at 5,000 bars even though the lower-level CSV parser can validate larger files.

Core research uses local CSVs or bundled synthetic fixtures. No provider account is required. The fixture market series has 520 daily bars; the weather fixture has explicit observation and publication times. Both are generated illustrations with redistributable provenance in [NOTICE](../NOTICE.md), not historical performance data.

## Local CSV contracts

Market columns:

```csv
timestamp,open,high,low,close,volume
2024-01-01T00:00:00Z,100,110,95,105,1000
2024-01-02T00:00:00Z,106,112,100,108,1200
```

`timestamp` is the bar's **opening** timestamp, with an explicit timezone; UTC is recommended. All prices must be finite and positive, high/low must contain open/close, volume is optional and nonnegative. At least two strictly increasing bars are required. Duplicate or unsorted bars are rejected rather than guessed into order. Interactive imports are bounded to 100,000 bars. Choose the actual interval in the strategy configuration; the app cannot infer publication semantics from a column name.

External observation columns:

```csv
observed_at,available_at,value,field,location
2024-01-01T06:00:00Z,2024-01-01T09:00:00Z,3.5,temperature,My town
```

Observation and availability must be timezone-aware; availability cannot precede observation. `field` and `location` are optional. Revisions can share an observation time if publication times differ. Duplicate identical observation/availability/field/location keys are rejected. Only values published by decision time are eligible; a configurable age limit prevents silent stale carry-forward. Select a location when several are present. Do not relabel arbitrary external events as OHLC candles.

Dataset fingerprints hash normalized content, so changing a market value or event revision changes research identity. Provider metadata and limitations should accompany any imported data. The software cannot establish that a user-provided publication timestamp is historically correct.

## Optional connectors

| Provider | Purpose and access | Constraints and labels |
| --- | --- | --- |
| Open-Meteo historical API | Opt-in historical weather by explicit coordinates and dates; no key for qualifying noncommercial use. | Reanalysis/revised observations, not point-in-time releases. Coverage includes ERA5 from 1940, ERA5-Land from 1950 and newer IFS from 2017. Free service quotas are fewer than 10,000/day, 5,000/hour, 600/minute. CC BY 4.0 data requires attribution; commercial service use needs appropriate terms. |
| Kraken public OHLC | Manual read-only snapshot of recent completed market bars; no private account key. | At most 720 recent entries and the current uncommitted entry is discarded. Rate limits apply by IP/pair; official support advises no faster than one request/second. The app's manual refresh is not a low-latency streaming feed. No blanket redistribution rights are claimed. |
| Alpha Vantage | Optional keyed `GLOBAL_QUOTE` connection test for one equity symbol. | Standard data is end-of-day, normally 25 calls/day. Real-time and 15-minute US entitlements are premium. A successful test does not enable historical training data or unrestricted commercial redistribution. |

Connector requests are sent from the Python backend to fixed provider endpoints, so browser CORS is not relied upon. No universal CORS support claim is made. Providers can refuse requests, change quotas or become unavailable; local experiments and fixtures continue to work. Network failures and quota responses must not be mistaken for empty valid datasets. No original downloaded third-party datasets are bundled in the release.

The Open-Meteo connector records `available_at` as the actual acquisition time, rather than inventing a historical publication time. Its daily mean observation is timestamped at the end of that UTC day. Consequently, freshly acquired reanalysis cannot generate historical trades before acquisition in the point-in-time event join. This makes the connector useful for inspecting/importing data while keeping the historically executable weather example grounded in fixtures with known availability.

Verified sources on 2026-10-28: [Open-Meteo historical documentation](https://open-meteo.com/en/docs/historical-weather-api), [Open-Meteo terms](https://open-meteo.com/en/terms), [Kraken OHLC contract](https://docs.kraken.com/api-reference/market-data/get-ohlc-data), [Kraken rate limits](https://support.kraken.com/gb/articles/206548367-what-are-the-api-rate-limits-), [Kraken API terms reminder](https://docs-legacy.kraken.com/api/docs/guides/global-intro/), [Alpha Vantage quote API](https://www.alphavantage.co/documentation/#latestprice), [Alpha Vantage quota/key support](https://www.alphavantage.co/support/).

## Add a provider in Python

A provider converts its response into validated `list[Bar]` or `list[Event]` records and supplies truthful provenance/availability warnings. Keep authentication, retries, request bounds and service errors inside the provider boundary. Consumers use the shared records and execution interface. Do not change the simulator to support a new timestamped external dataset. See [public APIs](api/index.md).
