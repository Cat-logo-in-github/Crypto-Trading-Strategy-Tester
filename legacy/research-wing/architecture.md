# Research Wing Architecture

## Vision

Research Wing is a modular quantitative research and market simulation framework.

The objective is to simulate realistic market conditions while remaining
fully extensible for:

- Classical rule-based strategies
- Machine learning strategies
- Reinforcement learning agents
- Multi-asset portfolios
- Alternative data
- Live trading (future)

---

# High-Level Architecture

```
Raw Data
    ↓
Downloader
    ↓
Cleaner
    ↓
Data Loader
    ↓
Candle Model
    ↓
Market
    ↓
Indicator Engine
    ↓
Strategy
    ↓
Signal
    ↓
Broker
    ↓
Order
    ↓
Matcher
    ↓
Trade
    ↓
Position
    ↓
Account
    ↓
Portfolio
    ↓
Backtester
    ↓
BacktestResult
    ↓
Evaluator
    ↓
Research Report
    ↓
Visualization
```

---

# Core Principles

## Single Responsibility

Every component solves one domain problem.

Examples:

- `Candle` stores market data.
- `Market` provides deterministic time progression.
- `Strategy` produces Signals.
- `Broker` constructs Orders.
- `Matcher` converts Orders into Trades.
- `Portfolio` tracks ownership and cash.

---

## Immutable Historical Data

Historical candles are immutable.

No component may modify past market records or use future candles.

---

## Event Driven

The simulation advances one candle at a time.

Each backtest iteration observes the current candle, updates indicators,
produces a signal, and then optionally executes an order.

Future support includes:

- Tick data
- Order book events
- News events

---

## Strategy Isolation

Strategies never:

- modify the portfolio
- fill orders
- calculate fees
- decide execution details

Strategies only observe state and emit Signals.

---

## Broker Isolation

The Broker converts strategy intent into executable Orders.

It decides:

- order side
- order quantity
- order type

It does not decide:

- execution fills
- fees
- slippage
- latency
- portfolio accounting

---

## Portfolio Isolation

The Portfolio only knows:

- cash
- positions
- realized PnL
- unrealized PnL

Portfolio state changes only through executed Trades.

---

## Indicator Isolation

Indicators compute features from market history.

They do not place trades or mutate portfolio state.

---

## Data Isolation

Raw market data, cleaned data, and processed Candle objects are separated.

This ensures reproducible research and enables independent improvements to:

- acquisition
- validation
- normalization
- simulation

---

# Engine Flow

Raw Data
↓
Downloader
↓
Cleaner
↓
Data Loader
↓
Market
↓
Indicator Engine
↓
Strategy
↓
Signal
↓
Broker
↓
Order
↓
Matcher
↓
Trade
↓
Portfolio
↓
Backtester
↓
BacktestResult
↓
Evaluator
↓
Visualization

---

# Canonical Data Models

## Candle

Immutable OHLCV bar used throughout the engine.

Converts raw market data into a stable research primitive.

---

## Signal

Represents strategy intent.

Signals describe desired portfolio exposure:

- LONG
- SHORT
- EXIT_LONG
- EXIT_SHORT
- HOLD

Signals do not include execution details.

The Broker converts Signals into Orders.

---

## StrategyContext

Read-only snapshot provided to strategies.

Contains:

- current candle
- historical candles available before the current bar
- portfolio equity
- cash
- positions
- indicator values

Does not contain:

- future data
- execution state
- broker internals
- pending orders

---

## Order  (Present in Engine)

Executable instruction created by the Broker from a Signal.

Unlike Signal, Order contains execution details:

- side (BUY / SELL)
- order type
- quantity
- limit / stop prices
- filled quantity
- fill status
- average fill price
- fees

Orders are mutable because execution updates their state.

---

## Trade (Present in Engine)

Immutable record of a completed Execution.

Trades are created by the Matcher from filled Orders.

They include:

- executed side
- symbol
- quantity
- execution price
- fees
- timestamp

Trades are the only events that mutate Portfolio state.

---

## Position (Present in Engine)

Represents current ownership of an asset.

Positions are derived from Trades and track:

- signed quantity
- average entry price
- realized PnL
- last update timestamp

---

## Account

Tracks cash and realized profit/loss.

Account manages money; Portfolio manages ownership.

---

## Portfolio

Central state container for Account, Positions, and Trade history.

It calculates:

- marked-to-market equity
- market exposure
- open positions

Portfolio state is updated only through `apply_trade()`.

---

___
# Working
___

## Market

Deterministic sequential market data provider.

The Market exposes:

- current candle
- historical candles without lookahead
- timestamp
- `step()` progression

The Market is not a trading engine.

---

## Data Loader

The single entry point for historical datasets used by the engine.

It orchestrates:

- raw data retrieval
- dataset cleaning and validation
- processed caching
- conversion into Candle objects

---

## Downloader

Acquires immutable raw market data from providers.

The downloader persists raw JSON and CSV archive files and supports
provider registration for future sources.

---

## Cleaner

Validates and sanitizes raw OHLCV data.

It removes duplicates, invalid OHLC records, negative volume, and
detects gaps.

---

## Indicator Engine

Computes indicator values separately from strategies.

Indicators are updated on each candle and exposed through StrategyContext.

---

## Broker

Translates Signals into executable Orders.

It uses a read-only broker context instead of direct Portfolio access.

---

## Execution Context

Provides a restricted view of portfolio state to execution components.

Example: `PortfolioBrokerContext` exposes equity, market prices, and
position quantity without allowing mutation.

---

## Matcher

Simulates order execution.

The Matcher applies:

- latency
- slippage
- fees

and converts filled Orders into immutable Trades.

---

## Fee Model

Isolated fee calculation interface.

Current implementations include zero fees and percentage fees.

---

## Slippage Model

Isolated execution price adjustment.

Current implementations include no slippage and percentage-based slippage.

---

## Latency Model

Isolated execution timestamp adjustment.

Current implementations include zero latency and fixed delays.

---

## Backtester

Coordinates the simulation loop.

It delegates domain-specific behavior to Market, Strategy, Broker,
Matcher, Portfolio, and Indicator Engine.

---

## BacktestResult

Immutable output of a completed simulation.

It contains equity history, executed trades, final cash, final equity,
and final portfolio snapshots.

---

## Evaluator

Transforms BacktestResult into research-ready reports.

It calculates performance, risk, trade statistics, and closed trade
analytics without mutating simulation state.

---

## Visualization

Consumes evaluation output and results to render dashboards,
equity curves, drawdowns, market overlays, and statistics.

Visualization is decoupled from core engine logic.

---

# Current Status

Completed:

- Candle model
- Data downloader + provider abstraction
- Data cleaner
- Data loader
- Market simulation
- Indicator engine
- Strategy signal pipeline
- Broker order creation
- Matcher execution simulation
- Fee / slippage / latency models
- Account, position, portfolio accounting
- Backtester orchestration
- Immutable backtest results
- Evaluator and research report pipeline
- Visualization components and dashboard

In Progress:

- advanced strategy families
- expanded market data providers
- more execution models
- richer evaluation and reporting
