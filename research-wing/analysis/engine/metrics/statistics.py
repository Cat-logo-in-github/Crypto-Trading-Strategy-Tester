"""
analysis.engine.metrics.statistics

Execution statistics calculations.

This module calculates execution-level statistics
from completed executions.

Functions in this module are pure.

They do not:

- access portfolio state
- access market data
- calculate performance
- modify simulation state

They transform immutable Trade records into an
immutable ExecutionStatistics summary.
"""

from __future__ import annotations

from collections.abc import Sequence

from analysis.engine.models.statistics import (
    ExecutionStatistics,
)
from analysis.engine.trade import Trade


def calculate(
    trades: Sequence[Trade],
) -> ExecutionStatistics:
    """
    Calculate execution statistics.

    Parameters
    ----------
    trades
        Immutable execution history.

    Returns
    -------
    ExecutionStatistics
        Immutable execution summary.
    """

    if not trades:

        return ExecutionStatistics(
            trade_count=0,
            buy_count=0,
            sell_count=0,
            total_fees=0.0,
            average_trade_value=0.0,
            largest_trade_value=0.0,
        )

    trade_values = [
        trade.value
        for trade in trades
    ]

    return ExecutionStatistics(
        trade_count=len(trades),

        buy_count=sum(
            trade.is_buy
            for trade in trades
        ),

        sell_count=sum(
            trade.is_sell
            for trade in trades
        ),

        total_fees=sum(
            trade.fees
            for trade in trades
        ),

        average_trade_value=(
            sum(trade_values)
            /
            len(trade_values)
        ),

        largest_trade_value=max(
            trade_values
        ),
    )