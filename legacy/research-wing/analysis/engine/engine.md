# Engine Components

---

## Market

Provides deterministic access to historical market data.

The Market is responsible for:

- maintaining simulation time
- exposing the current candle
- providing historical data without future leakage
- advancing the simulation one event at a time

The Market is intentionally passive.

It does not:

- execute trades
- manage portfolios
- calculate indicators
- generate signals

Its sole responsibility is presenting an immutable historical timeline to the rest of the engine.

---

## Backtester

Coordinates the complete research simulation.

The Backtester orchestrates the interaction between:

- Market
- Strategy
- Portfolio

For each market event it:

1. constructs a read-only `StrategyContext`
2. invokes the strategy
3. executes resulting signals
4. updates portfolio state
5. advances market time

The Backtester owns the simulation loop but delegates domain-specific logic to specialized components.

Future versions will delegate execution to the Broker and Execution Engine while preserving the same orchestration role.
