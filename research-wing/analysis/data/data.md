# Data Layer

The data layer is partioned into 3 layers. Individualy accountable for one responsiblity:

---
## Data Downloader

Responsible for acquiring immutable raw market data from external providers.

Responsibilities:

- selecting the appropriate data provider
- fetching historical market data
- persisting raw datasets in JSON and CSV formats
- supporting authenticated and public API endpoints
- exposing a provider interface for future exchanges and data sources

The downloader performs **no validation, normalization, or cleaning**. It is solely responsible for reproducible data acquisition.

---

## Data Cleaner

Responsible for validating and normalizing raw OHLCV datasets before they enter the simulation engine.

Responsibilities:

- validating OHLC integrity
- removing duplicate candles
- removing invalid market records
- detecting missing time intervals
- producing deterministic cleaned datasets
- generating dataset quality diagnostics

The cleaner never downloads or transforms business logic beyond data integrity checks.

---

## Data Loader

The Data Loader is the single entry point for historical datasets used by the engine.

Responsibilities:

- orchestrating dataset acquisition
- managing raw and processed caches
- invoking the downloader when required
- invoking the cleaner for validation
- converting cleaned records into immutable `Candle` objects

The rest of the engine interacts only with the Data Loader and remains independent of external data sources.

---