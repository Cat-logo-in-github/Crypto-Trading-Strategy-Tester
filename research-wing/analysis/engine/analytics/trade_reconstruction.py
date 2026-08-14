"""
analysis.engine.analytics.trade_reconstruction

Trade lifecycle reconstruction.

Converts execution-level Trades into
completed ClosedTrades.

Trade:
    - single execution event

ClosedTrade:
    - completed position lifecycle

This module belongs to the research layer.
It never modifies Portfolio or simulation state.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence

from analysis.engine.trade import (
    Trade,
    TradeSide,
)

from analysis.engine.models.closed_trade import (
    ClosedTrade,
)



@dataclass
class _OpenPosition:
    """
    Internal reconstruction state.

    Represents currently open exposure
    while processing execution history.
    """

    symbol: str

    direction: TradeSide

    quantity: float

    average_price: float

    entry_trade: Trade

    allocated_fees: float = 0.0



def reconstruct_closed_trades(
    trades: Sequence[Trade],
) -> tuple[ClosedTrade, ...]:
    """
    Convert executions into completed trades.

    Uses FIFO-style lifecycle tracking.

    Parameters
    ----------
    trades:
        Completed executions.

    Returns
    -------
    tuple[ClosedTrade, ...]
        Completed position outcomes.
    """

    open_positions: dict[
        str,
        _OpenPosition,
    ] = {}


    closed: list[ClosedTrade] = []


    counter = 0



    for trade in trades:

        position = (
            open_positions.get(
                trade.symbol
            )
        )



        # -----------------------------------------
        # No existing exposure
        # -----------------------------------------

        if position is None:

            open_positions[
                trade.symbol
            ] = _OpenPosition(

                symbol=trade.symbol,

                direction=trade.side,

                quantity=trade.quantity,

                average_price=trade.price,

                entry_trade=trade,

                allocated_fees=trade.fees,
            )

            continue



        # -----------------------------------------
        # Same direction = add exposure
        # -----------------------------------------

        if position.direction is trade.side:

            total_quantity = (
                position.quantity
                +
                trade.quantity
            )


            position.average_price = (

                (
                    position.quantity
                    *
                    position.average_price
                )
                +
                (
                    trade.quantity
                    *
                    trade.price
                )

            ) / total_quantity


            position.quantity = (
                total_quantity
            )


            position.allocated_fees += (
                trade.fees
            )


            continue



        # -----------------------------------------
        # Opposite direction = close
        # -----------------------------------------

        close_quantity = min(
            position.quantity,
            trade.quantity,
        )


        fee_fraction = (
            close_quantity
            /
            trade.quantity
        )


        exit_fees = (
            trade.fees
            *
            fee_fraction
        )


        entry_fees = (
            position.allocated_fees
            *
            (
                close_quantity
                /
                position.quantity
            )
        )


        gross_pnl = _calculate_pnl(
            position,
            trade.price,
            close_quantity,
        )


        counter += 1


        closed.append(
            ClosedTrade(

                id=(
                    f"{trade.symbol}-"
                    f"{counter}"
                ),

                symbol=trade.symbol,

                entry_trade=(
                    position.entry_trade
                ),

                exit_trade=trade,

                quantity=close_quantity,

                gross_pnl=gross_pnl,

                fees=(
                    entry_fees
                    +
                    exit_fees
                ),
            )
        )


        # -----------------------------------------
        # Reduce open position
        # -----------------------------------------

        position.quantity -= (
            close_quantity
        )


        position.allocated_fees -= (
            entry_fees
        )


        remaining_quantity = (
            trade.quantity
            -
            close_quantity
        )



        # Fully closed
        if position.quantity == 0:

            del open_positions[
                trade.symbol
            ]



        # -----------------------------------------
        # Flip into opposite position
        # -----------------------------------------

        if remaining_quantity > 0:

            open_positions[
                trade.symbol
            ] = _OpenPosition(

                symbol=trade.symbol,

                direction=trade.side,

                quantity=remaining_quantity,

                average_price=trade.price,

                entry_trade=trade,

                allocated_fees=(
                    trade.fees
                    -
                    exit_fees
                ),
            )


    return tuple(closed)



def _calculate_pnl(
    position: _OpenPosition,
    exit_price: float,
    quantity: float,
) -> float:
    """
    Calculate gross realized PnL.
    """

    if position.direction is TradeSide.BUY:

        return (
            exit_price
            -
            position.average_price
        ) * quantity


    return (
        position.average_price
        -
        exit_price
    ) * quantity