"""
analysis.engine.metrics.performance

Performance calculations.

This module converts a completed backtest result
into a performance summary.

It does not:
- access portfolio state
- execute trades
- modify simulation data

It only performs pure calculations.
"""

from __future__ import annotations

from analysis.engine.results import BacktestResult
from analysis.engine.models.performance import PerformanceSummary

from analysis.engine.metrics import (
    returns,
    drawdown,
)



def calculate(
    result: BacktestResult,
) -> PerformanceSummary:
    """
    Calculate portfolio performance.

    Parameters
    ----------
    result:
        Completed backtest output.

    Returns
    -------
    PerformanceSummary
        Immutable performance statistics.
    """

    return PerformanceSummary(

        initial_equity=(
            result.initial_equity
        ),

        final_equity=(
            result.ending_equity
        ),

        total_return=(
            returns.total_return(
                result.equity_curve
            )
        ),

        peak_equity=(
            drawdown.peak_equity(
                result.equity_curve
            )
        ),

        max_drawdown=(
            drawdown.max_drawdown(
                result.equity_curve
            )
        ),

        executions=(
            result.execution_count
        ),
    )