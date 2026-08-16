"""
analysis.engine.metrics.trades

Completed trade analytics.

Calculates strategy-level trade statistics
from ClosedTrade objects.

This module:
- performs calculations
- does not modify state
- does not access simulation objects
"""

from __future__ import annotations

from collections.abc import Sequence

from analysis.engine.models.closed_trade import (
    ClosedTrade,
)

from analysis.engine.models.trade_statistics import (
    TradeStatistics,
)



def calculate(
    trades: Sequence[ClosedTrade],
) -> TradeStatistics:
    """
    Calculate completed trade statistics.

    Parameters
    ----------
    trades:
        Completed position lifecycles.

    Returns
    -------
    TradeStatistics
        Immutable trade analytics summary.
    """

    if not trades:

        return TradeStatistics(
            total_trades=0,

            winning_trades=0,

            losing_trades=0,

            win_rate=0.0,

            gross_profit=0.0,

            gross_loss=0.0,

            profit_factor=0.0,

            average_trade=0.0,

            expectancy=0.0,

            average_win=0.0,

            average_loss=0.0,

            average_holding_time_seconds=0.0,
        )


    winners = [
        trade
        for trade in trades
        if trade.is_winner
    ]


    losers = [
        trade
        for trade in trades
        if trade.is_loser
    ]


    gross_profit = sum(
        trade.net_pnl
        for trade in winners
    )


    gross_loss = sum(
        trade.net_pnl
        for trade in losers
    )


    total_pnl = sum(
        trade.net_pnl
        for trade in trades
    )


    average_trade = (
        total_pnl
        /
        len(trades)
    )


    average_win = (
        gross_profit
        /
        len(winners)
        if winners
        else 0.0
    )


    average_loss = (
        gross_loss
        /
        len(losers)
        if losers
        else 0.0
    )


    profit_factor = (
        gross_profit
        /
        abs(gross_loss)
        if gross_loss != 0
        else 0.0
    )


    expectancy = average_trade


    holding_time = sum(
        (
            trade.holding_period.total_seconds()
            if hasattr(trade.holding_period, "total_seconds")
            else float(trade.holding_period) / 1000.0
        )
        for trade in trades
    )


    return TradeStatistics(

        total_trades=len(trades),

        winning_trades=len(winners),

        losing_trades=len(losers),

        win_rate=(
            len(winners)
            /
            len(trades)
        ),

        gross_profit=gross_profit,

        gross_loss=gross_loss,

        profit_factor=profit_factor,

        average_trade=average_trade,

        expectancy=expectancy,

        average_win=average_win,

        average_loss=average_loss,

        average_holding_time_seconds=(
            holding_time
            /
            len(trades)
        ),
    )