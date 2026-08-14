# Models

## Purpose

The Models subsystem defines the canonical, immutable data structures used across the engine.

Models provide a shared language between components such as:

- Market
- Strategy
- Broker
- Matcher
- Portfolio
- Evaluator
- Visualization

## Design Principles

- Models should be immutable whenever they represent historical records.
- Validation should be performed on construction.
- Models should encapsulate only data and derived read-only helpers.
- Business logic should remain separate from model definitions.

## Core Models

### Candle

`Candle` is the canonical OHLCV bar used throughout the engine.

Properties:

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

Derived helpers include:

- `hl2`
- `hlc3`
- `ohlc4`
- `weighted_close`
- `body`
- `range`
- `upper_wick`
- `lower_wick`
- `bullish`
- `bearish`
- `doji`

### Signal

`Signal` represents strategy intent and is intentionally not an order.

Properties:

- `timestamp`
- `symbol`
- `action` (`LONG`, `SHORT`, `EXIT_LONG`, `EXIT_SHORT`, `HOLD`)
- `quantity`
- `sizing` (`UNITS`, `PERCENT_EQUITY`, `PERCENT_POSITION`)
- `confidence`
- optional `stop_loss` and `take_profit`

Signals are produced by strategies and consumed by the Broker.

### PositionSnapshot and Position

`PositionSnapshot` is an immutable historical snapshot used in reporting.

`Position` is the mutable current state of an asset position.

They track:

- signed quantity
- average entry price
- realized pnl
- last update timestamp

Positions are updated only via executed Trades.

### Trade

`Trade` is an immutable execution record created by the Matcher.

It includes:

- `id`
- `order_id`
- `timestamp`
- `symbol`
- `side`
- `quantity`
- `price`
- `fees`

### ClosedTrade

`ClosedTrade` represents a completed round-trip trade.

It is composed from entry and exit `Trade` records and used for trade-level analytics.

### PerformanceSummary

Immutable performance metrics produced by the metrics subsystem.

### RiskSummary

Immutable risk metrics produced by the risk subsystem.

### ExecutionStatistics

Immutable execution summary from trade records.

### ResearchReport

`ResearchReport` is the canonical evaluation output.

It aggregates performance, risk, execution statistics, closed trades, equity curves, candles, and benchmark results.

## Model Usage

Models are the shared data contracts of the pipeline.

Examples:

- `DataLoader` converts raw data into `Candle` models.
- `Market` iterates over `Candle` models.
- `StrategyContext` exposes `Candle` and indicator values to strategies.
- `Broker` converts `Signal` into `Order`.
- `Matcher` converts `Order` into `Trade`.
- `Portfolio` updates positions from `Trade`.
- `Evaluator` converts `BacktestResult` into `ResearchReport`.

## Why models matter

Using explicit models ensures:

- consistent data semantics
- safer simulation boundaries
- clearer architecture
- easier debugging
- portable research output
