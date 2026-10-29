"""
analysis.engine.metrics.equity

Portfolio equity models.

Equity represents the mark-to-market value of the portfolio
at a specific point during a backtest.

The equity curve forms the basis for performance analysis,
including:

- total return
- drawdown
- volatility
- Sharpe ratio
- Calmar ratio

The models in this module are passive data containers.
They do not perform any calculations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class EquityPoint:
    """
    Snapshot of portfolio value.

    Recorded once per simulation step after all executions
    for that candle have completed.

    Parameters
    ----------
    timestamp:
        Simulation timestamp.

    equity:
        Total marked-to-market portfolio value.

    cash:
        Available cash after execution.
    """

    timestamp: datetime

    equity: float

    cash: float

    def __post_init__(self) -> None:
        """
        Validate equity snapshot.
        """

        if self.equity < 0:
            raise ValueError(
                "Equity cannot be negative."
            )

        if self.cash < 0:
            raise ValueError(
                "Cash cannot be negative."
            )

    @property
    def invested(self) -> float:
        """
        Capital currently invested.

        Defined as:

            equity - cash
        """

        return self.equity - self.cash

    def __repr__(self) -> str:

        return (
            "EquityPoint("
            f"time={self.timestamp}, "
            f"equity={self.equity:.2f}, "
            f"cash={self.cash:.2f}"
            ")"
        )