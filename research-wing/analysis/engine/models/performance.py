"""
analysis.engine.models.performance

Performance result models.

Immutable data containers used by
the research and evaluation layers.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PerformanceSummary:
    """
    Immutable performance evaluation result.

    Contains metrics calculated from a completed
    backtest.

    Trade-level statistics are intentionally
    excluded until closed trade tracking exists.
    """

    initial_equity: float

    final_equity: float

    total_return: float

    peak_equity: float

    max_drawdown: float

    executions: int