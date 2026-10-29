# Architectural Decisions

## Decision 001

Historical candles are immutable.

Reason:

Historical data should never change during a simulation.

Implementation:

`@dataclass(frozen=True, slots=True)`

---

## Decision 002

Strategies return Signals instead of Orders.

Reason:

Strategies should express intent, not execution.

Execution depends on:

- slippage
- commissions
- liquidity
- latency

which are handled by the Broker.

---
## Decision 003

Strategies produce Signals instead of Orders.

Reason:

Signals represent trading intent only.

Execution details such as order type, fill price, slippage, latency,
commissions, and partial fills are the responsibility of the Broker.

This separation keeps strategies execution-agnostic and allows the same
strategy to operate under different execution models.

---
## Decision 004

Signals represent exposure intent, not buy/sell instructions.

Reason:

BUY/SELL is execution terminology and differs between:
- spot markets
- margin markets
- futures
- derivatives

Using LONG/SHORT separates strategy logic from execution mechanics.

---
## Decision 005

StrategyContext is the strategy observation boundary.

Reason:

Strategies should only observe market state and produce Signals.

StrategyContext provides:

- current candle
- historical candles
- portfolio state
- indicators

It prevents:

- strategy access to broker internals
- accidental state mutation
- look-ahead bias

Implementation:

`StrategyContext` is read-only (`frozen=True`).

---
## Decision 006

Orders are separate from Signals.

Reason:

Signals represent strategy intent.

Orders represent executable instructions and contain:

- side
- order type
- fill state
- execution prices

The Broker converts Signals into Orders.

---
## Decision 007

Orders and Trades are separate entities.

Reason:

Orders represent execution requests.

Trades represent executions that actually occurred.

Orders can be:
- rejected
- cancelled
- partially filled

Trades are immutable records created only after execution.

---
## Decision 008

Positions are derived from Trades.

Reason:

Trades represent immutable execution history.

Positions represent current state built from those executions.

The Portfolio owns Positions, not Orders.

---
## Decision 009

Account and Portfolio are separate.

Reason:

Account tracks money.

Portfolio tracks ownership.

Separating them allows realistic handling of:

- cash
- positions
- PnL
- deposits
- withdrawals

---
## Decision 010

Portfolio state changes only through Trades.

Reason:

Orders may fail or remain pending.

Trades represent actual execution.

Therefore:

Trade → Position → Portfolio

is the state update path.

---
## Decision 011

Market is the single source of simulation time.

Reason:

Simulation time must advance consistently for every component.

Strategies, indicators, brokers, and portfolios should never maintain independent clocks.

The Market owns the current timestamp and exposes historical data corresponding to that instant.

This guarantees deterministic replay and prevents accidental look-ahead bias.

Implementation:

The Market advances only through `step()` and exposes historical data exclusively through `history()`.

---
## Decision 012

The Backtester is an orchestrator rather than a business-logic container.

Reason:

The Backtester should coordinate simulation flow without owning trading logic.

Individual responsibilities remain isolated:

- Market provides data.
- Strategy generates Signals.
- Broker executes Orders.
- Portfolio updates state from Trades.

Keeping the Backtester focused on orchestration simplifies testing, enables component replacement, and allows more sophisticated execution models without changing the simulation loop.

Implementation:

The Backtester constructs a `StrategyContext`, invokes the strategy, processes the resulting signal, and advances the simulation while delegating domain-specific behavior to other engine components.

---
## Decision 013

Raw market data is stored separately from processed datasets.

Reason:

Downloaded market data should remain an immutable archive of the original provider response.

Cleaning and normalization are performed on copies, allowing improvements to preprocessing without requiring another download.

---

## Decision 014

Market data acquisition uses a provider abstraction.

Reason:

Different exchanges and data vendors expose different APIs.

A provider interface allows new sources to be added without modifying the downloader core, improving extensibility and reducing coupling.

---

## Decision 015

Dataset validation is separated from data acquisition.

Reason:

Downloading data and validating data are distinct responsibilities.

The downloader preserves provider responses exactly as received, while the cleaner enforces data integrity rules before the engine consumes the dataset.

This separation keeps preprocessing deterministic and independently testable.

---

## Decision 016

The Data Loader is the only entry point for historical market data.

Reason:

Centralizing dataset orchestration guarantees consistent caching, validation, normalization, and conversion into engine data models.

Engine components should never communicate directly with external APIs or raw storage.

Implementation:

`DataLoader.load()` orchestrates raw download, cleaning, processing, and conversion into immutable `Candle` objects.

---

## Decision 017

Execution logic is separated into Broker and Matcher.

Reason:

Order creation and order execution represent different responsibilities.

The Broker understands:

- strategy intent
- position sizing
- order construction

The Matcher understands:

- market execution
- fills
- costs
- execution timing

Separating these allows different execution models without modifying strategies.

Implementation:
Signal → Broker → Order → Matcher → Trade

---

## Decision 018

The Broker cannot directly access Portfolio internals.

Reason:

Execution components should depend on minimal information rather than application state.

The Broker only requires:

- equity
- positions
- prices

A context adapter provides this information without exposing mutation.

Benefits:

- easier testing
- lower coupling
- safer architecture

Implementation:

`PortfolioBrokerContext` acts as a restricted execution view.
---


## Decision 019

Trades are the only execution events that mutate portfolio state.

Reason:

Orders represent requested execution.

They may:

- fail
- be cancelled
- partially fill

Only completed executions represent ownership changes.

Therefore:
Order → Trade → Portfolio


is the only valid state transition path.

---

## Decision 020

Execution costs are modeled independently.

Reason:

Fees, slippage, and latency are exchange-specific behavior.

They should not be embedded inside:

- strategies
- brokers
- portfolios

Separating cost models allows realistic simulation changes without rewriting the trading system.

Implementation:
Matcher
|
+-- FeeModel
|
+-- SlippageModel
|
+-- LatencyModel


---

## Decision 021

Execution models are deterministic transformations.

Reason:

Research simulations must be reproducible.

Latency, fees, and slippage models should transform inputs into outputs without:

- external clocks
- hidden state
- random behavior unless explicitly configured

This guarantees that identical inputs produce identical executions.

---

## Decision 022

The execution engine supports replacement through interfaces.

Reason:

Different markets require different execution behavior.

Examples:

- cryptocurrency exchanges
- equities
- futures
- high-frequency simulation

Abstract interfaces allow replacing:

- fee models
- slippage models
- latency models

without changing:

- strategies
- portfolio accounting
- backtesting flow

---

## Decision 023

Results are immutable boundaries between simulation and evaluation.

Reason:

Evaluation should consume stable outputs rather than engine internals.

Immutable results ensure reproducible reports and simplify analysis.

Implementation:

`BacktestResult` is a frozen dataclass containing equity history, trades, final cash, and final positions.

---

## Decision 024

Evaluation is a read-only transformation of completed results.

Reason:

Metrics and reports should not mutate simulation state.

Evaluation is a separate concern from execution.

Implementation:

`Evaluator.evaluate()` computes performance, risk, trade statistics, and closed trade analytics from `BacktestResult`.

---

## Decision 025

Indicators are separate feature engines.

Reason:

Indicator computation should not be mixed with trading decisions or execution logic.

This supports cleaner strategy design and easier reuse.

Implementation:

`IndicatorEngine` updates indicator values on each candle and exposes them through `StrategyContext`.

---

## Decision 026

Visualization consumes analysis output, not engine internals.

Reason:

Charts and dashboards should render results from completed simulations and reports.

This keeps visualization decoupled from core research logic.

Implementation:

Visualization components render equity, drawdown, trade overlay, and statistics from report and result models.


Centralizing dataset orchestration guarantees consistent caching, validation, normalization, and conversion into engine data models.

Engine components should never communicate directly with external APIs or raw storage, ensuring reproducible simulations and a single source of truth for historical data.

---




Future decisions will be documented here.