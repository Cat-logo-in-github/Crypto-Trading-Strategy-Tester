"""
analysis.engine.models.trade_statistics

Completed trade analytics model.

Contains strategy outcome statistics
calculated from ClosedTrade objects.

This model contains data only.
No calculations.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TradeStatistics:
    """
    Immutable completed trade statistics.
    """

    total_trades: int

    winning_trades: int

    losing_trades: int

    win_rate: float

    gross_profit: float

    gross_loss: float

    profit_factor: float

    average_trade: float

    expectancy: float

    average_win: float

    average_loss: float

    average_holding_time_seconds: float