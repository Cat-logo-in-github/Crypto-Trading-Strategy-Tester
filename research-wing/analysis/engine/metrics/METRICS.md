# Metrics

## Purpose

The Metrics subsystem converts completed backtest results into quantitative summaries that support evaluation, reports, and visualization.

Metrics are calculated after the simulation has finished. They operate on immutable output such as `BacktestResult`, `Trade`, and `EquityPoint`.

## Design Principles

- Metrics are pure, read-only calculations.
- They do not mutate simulation state.
- They do not execute trades or access order lifecycle data directly.
- They work from completed results and historical execution records.

## Architecture

### Performance Metrics

Performance metrics summarize portfolio outcomes.

The performance module currently computes:

- initial equity
- final equity
- total return
- peak equity
- maximum drawdown
- execution count

These metrics are captured in `PerformanceSummary`.

### Risk Metrics

Risk metrics quantify volatility and risk-adjusted returns.

The risk module currently computes:

- annualized volatility
- annualized Sharpe ratio

These calculations operate on the equity curve only.

### Execution Statistics

Execution statistics summarize trade-level activity.

The statistics module currently computes:

- trade count
- buy count
- sell count
- total fees
- average trade value
- largest trade value

### Supporting Metrics

Additional supporting modules include:

- `drawdown` — peak equity and drawdown calculations
- `returns` — periodic return calculations
- `equity` — equity curve structures and helpers
- `trades` — completed trade statistics and closed trade analytics

## Usage

Metrics are typically invoked by the `Evaluator` after a backtest completes.

Example:

```python
from analysis.engine.metrics.performance import calculate as calculate_performance
performance = calculate_performance(backtest_result)
```

Or via the evaluator:

```python
from analysis.engine.evaluator import Evaluator
report = Evaluator().evaluate(backtest_result)
```

## Purpose in the Research Pipeline

Metrics provide the structured numbers that power:

- research reports
- dashboards
- strategy comparisons
- benchmark evaluation
- risk management analysis

They are the bridge between raw execution results and meaningful research insights.
