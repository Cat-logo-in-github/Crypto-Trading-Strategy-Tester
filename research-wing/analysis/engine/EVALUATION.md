# Evaluation

## Purpose

The Evaluation subsystem converts completed backtest output into research-ready reports.

It sits after the execution pipeline and provides the final summary used for:

- performance analysis
- risk assessment
- benchmark comparison
- trade analytics
- visualization

## Design Principles

- Evaluation operates on immutable simulation results.
- It does not execute or mutate trades, orders, or portfolio state.
- It is the single public entry point for research metrics.
- Reports are immutable and suitable for persistence and dashboarding.

## Architecture

### Evaluator

The `Evaluator` is the top-level coordinator of the evaluation pipeline.

Responsibilities:

- accept a `BacktestResult`
- optionally accept benchmark results and raw candles
- calculate performance metrics
- calculate risk metrics
- calculate execution statistics
- reconstruct closed trades
- calculate trade statistics
- assemble the final `ResearchReport`

### BacktestResult

`BacktestResult` is the immutable output of a finished simulation.

It contains:

- equity curve
- executed trades
- final cash
- final equity
- final positions snapshot
- simulation timestamps
- metadata

### ResearchReport

`ResearchReport` aggregates evaluation outputs into a single immutable object.

It includes:

- `performance`
- `risk`
- `benchmark`
- `execution_statistics`
- `closed_trades`
- `equity_curve`
- `candles`
- `trade_statistics`

## Evaluation Pipeline

1. `Evaluator.evaluate(result, benchmark, candles)`
2. compute performance summary
3. compute risk summary
4. compute execution statistics
5. reconstruct closed trades from trade history
6. calculate trade-level statistics
7. return a `ResearchReport`

## Current Implementation

Evaluation currently includes:

- performance metrics via `analysis.engine.metrics.performance`
- risk metrics via `analysis.engine.metrics.risk`
- execution statistics via `analysis.engine.metrics.statistics`
- closed trade reconstruction via `analysis.engine.analytics.trade_reconstruction`
- trade statistics via `analysis.engine.metrics.trades`

## Usage

Example:

```python
from analysis.engine.evaluator import Evaluator

report = Evaluator().evaluate(
    result=backtest_result,
    benchmark=benchmark_result,
    candles=tuple(raw_candles),
)
```

## Role in the Research Pipeline

Evaluation is the boundary between simulation and insight.

It transforms raw engine output into a stable report that can be:

- stored as experiment results
- displayed in dashboards
- compared across strategies
- used for risk review

Evaluation is intentionally separate from the execution engine so that metrics remain stable and reproducible.
