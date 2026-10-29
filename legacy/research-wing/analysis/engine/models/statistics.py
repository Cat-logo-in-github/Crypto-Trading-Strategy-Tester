"""
analysis.engine.models.statistics

Execution statistics models.

Immutable data containers describing execution
activity produced during a completed simulation.

These models contain no business logic.

They are constructed exclusively by the
evaluation metrics layer.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExecutionStatistics:
    """
    Immutable execution statistics.

    These statistics describe execution activity,
    not portfolio performance or closed-trade
    analytics.

    Future versions may extend this model with
    additional execution-level metrics while
    remaining independent from research-grade
    trade analytics.
    """

    trade_count: int

    buy_count: int

    sell_count: int

    total_fees: float

    average_trade_value: float

    largest_trade_value: float