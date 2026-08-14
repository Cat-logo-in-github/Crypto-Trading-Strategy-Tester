"""
analysis.engine.results

Backtest result models.

A BacktestResult represents the immutable output
of a completed simulation.

It forms the boundary between:

Simulation Engine
        |
        ▼
BacktestResult
        |
        ▼
Evaluation / Metrics / Reports

This module contains only data models.

It does not:
- calculate metrics
- evaluate strategies
- generate reports
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Mapping

from analysis.engine.metrics.equity import EquityPoint
from analysis.engine.position import PositionSnapshot
from analysis.engine.trade import Trade



@dataclass(frozen=True, slots=True)
class BacktestResult:
    """
    Immutable record of a completed backtest.

    A BacktestResult is a historical artifact.
    It contains simulation output, not analysis.

    Parameters
    ----------
    equity_curve:
        Portfolio mark-to-market history.

    trades:
        Immutable execution history.

    final_cash:
        Ending available cash.

    final_equity:
        Ending marked-to-market portfolio value.

    final_positions:
        Snapshot of ending portfolio ownership state.

    start_time:
        First simulation timestamp.

    end_time:
        Final simulation timestamp.

    metadata:
        Experiment metadata.
    """

    equity_curve: tuple[EquityPoint, ...]

    trades: tuple[Trade, ...]

    final_cash: float

    final_equity: float

    final_positions: Mapping[
        str,
        PositionSnapshot,
    ]

    start_time: datetime | None

    end_time: datetime | None

    metadata: Mapping[str, Any]


    def __post_init__(self) -> None:
        """
        Validate immutable result state.
        """

        if self.final_cash < 0:
            raise ValueError(
                "Final cash cannot be negative."
            )

        if self.final_equity < 0:
            raise ValueError(
                "Final equity cannot be negative."
            )


        object.__setattr__(
            self,
            "final_positions",
            MappingProxyType(
                dict(self.final_positions)
            ),
        )


        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(
                dict(self.metadata)
            ),
        )



    # --------------------------------------------------
    # Equity information
    # --------------------------------------------------

    @property
    def initial_equity(self) -> float:
        """
        Starting portfolio equity.
        """

        if not self.equity_curve:
            return 0.0

        return self.equity_curve[0].equity



    @property
    def ending_equity(self) -> float:
        """
        Final portfolio equity.

        Uses stored value rather than
        recalculating from market data.
        """

        return self.final_equity



    # --------------------------------------------------
    # Simulation information
    # --------------------------------------------------

    @property
    def execution_count(self) -> int:
        """
        Number of executed trades.
        """

        return len(self.trades)



    @property
    def start_timestamp(self) -> datetime | None:
        """
        First equity observation timestamp.
        """

        if not self.equity_curve:
            return None

        return self.equity_curve[0].timestamp



    @property
    def end_timestamp(self) -> datetime | None:
        """
        Last equity observation timestamp.
        """

        if not self.equity_curve:
            return None

        return self.equity_curve[-1].timestamp



    @property
    def duration(self) -> timedelta | None:
        """
        Total simulation duration.
        """

        start = self.start_timestamp
        end = self.end_timestamp

        if (
            start is None
            or end is None
        ):
            return None

        if isinstance(start, int) and isinstance(end, int):
            return timedelta(
                milliseconds=end - start
            )

        return end - start



    def __repr__(self) -> str:

        return (
            "BacktestResult("
            f"executions={self.execution_count}, "
            f"equity={self.final_equity:.2f}"
            ")"
        )