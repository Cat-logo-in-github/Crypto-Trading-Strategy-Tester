"""
analysis.engine.analytics.trade_reconstruction

Trade lifecycle reconstruction.

Converts execution-level Trades into research-level
ClosedTrades.

Execution layer
---------------

    Trade
        |
        | one execution
        v
    reconstruction
        |
        | lifecycle matching
        v
    ClosedTrade
        |
        v
    research statistics


Important distinction
---------------------

A Trade is an execution.

A ClosedTrade is a realized portion of a position.

Therefore:

    BUY 1.0
    SELL 0.25
    SELL 0.25
    SELL 0.50

produces THREE ClosedTrades.

It does NOT produce one full exit followed by two
additional exits.

The reconstruction layer is completely independent
of Portfolio state. It operates only on immutable
execution history.
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


# ============================================================
# Internal lifecycle state
# ============================================================


@dataclass(slots=True)
class _OpenLot:
    """
    Internal open-position lot.

    A lot represents an amount of exposure that has not
    yet been closed.

    Multiple entry executions are kept as separate lots.

    This gives us deterministic FIFO reconstruction.
    """

    trade: Trade
    quantity: float
    allocated_fees: float

    @property
    def direction(self) -> TradeSide:
        return self.trade.side

    @property
    def price(self) -> float:
        return self.trade.price


# ============================================================
# Public reconstruction API
# ============================================================


def reconstruct_closed_trades(
    trades: Sequence[Trade],
) -> tuple[ClosedTrade, ...]:
    """
    Reconstruct completed position portions from executions.

    Matching model
    --------------

    Same-direction execution:

        BUY + BUY
        SELL + SELL

    creates additional open exposure.

    Opposite-direction execution:

        BUY -> SELL
        SELL -> BUY

    closes existing exposure using FIFO lots.

    Partial exits are fully supported.

    Example
    -------

        BUY 1.0 @ 100
        SELL 0.25 @ 110
        SELL 0.25 @ 120
        SELL 0.50 @ 130

    produces:

        ClosedTrade(qty=0.25)
        ClosedTrade(qty=0.25)
        ClosedTrade(qty=0.50)

    If an opposite-side execution is larger than the current
    exposure, the excess quantity opens a new position in the
    opposite direction.

    Example
    -------

        BUY 1.0 @ 100
        SELL 1.5 @ 110

    produces:

        ClosedTrade(qty=1.0)

    and leaves:

        SHORT 0.5 @ 110

    open for future executions.

    Parameters
    ----------
    trades:
        Execution history in chronological order.

    Returns
    -------
    tuple[ClosedTrade, ...]
        Immutable collection of completed lifecycle portions.

    Notes
    -----
    The function does not mutate the supplied trades.
    It also does not mutate Portfolio or Position objects.
    """

    open_lots: dict[
        str,
        list[_OpenLot],
    ] = {}

    closed_trades: list[ClosedTrade] = []

    counter = 0

    for trade in trades:

        if trade.quantity <= 0:
            raise ValueError(
                "Trade quantity must be positive."
            )

        symbol_lots = open_lots.setdefault(
            trade.symbol,
            [],
        )

        remaining = trade.quantity

        # ----------------------------------------------------
        # No open exposure
        # ----------------------------------------------------

        if not symbol_lots:

            symbol_lots.append(
                _OpenLot(
                    trade=trade,
                    quantity=remaining,
                    allocated_fees=trade.fees,
                )
            )

            continue

        # ----------------------------------------------------
        # Same direction?
        #
        # If the first open lot has the same direction, this
        # execution adds exposure rather than closing it.
        #
        # Multiple same-direction executions remain separate
        # FIFO lots.
        # ----------------------------------------------------

        if symbol_lots[0].direction is trade.side:

            symbol_lots.append(
                _OpenLot(
                    trade=trade,
                    quantity=remaining,
                    allocated_fees=trade.fees,
                )
            )

            continue

        # ----------------------------------------------------
        # Opposite direction.
        #
        # Consume existing lots FIFO.
        # ----------------------------------------------------

        while (
            remaining > 0
            and symbol_lots
        ):

            lot = symbol_lots[0]

            close_quantity = min(
                lot.quantity,
                remaining,
            )

            # ----------------------------------------------
            # Allocate entry fees proportionally.
            # ----------------------------------------------

            entry_fee_fraction = (
                close_quantity
                /
                lot.quantity
            )

            entry_fees = (
                lot.allocated_fees
                *
                entry_fee_fraction
            )

            # ----------------------------------------------
            # Allocate exit fees proportionally.
            #
            # If one exit closes several lots, each ClosedTrade
            # receives its proportional share of that execution's
            # fees.
            # ----------------------------------------------

            exit_fee_fraction = (
                close_quantity
                /
                trade.quantity
            )

            exit_fees = (
                trade.fees
                *
                exit_fee_fraction
            )

            # ----------------------------------------------
            # Calculate gross realized P&L.
            # ----------------------------------------------

            gross_pnl = _calculate_pnl(
                entry_side=lot.direction,
                entry_price=lot.price,
                exit_price=trade.price,
                quantity=close_quantity,
            )

            counter += 1

            closed_trades.append(
                ClosedTrade(
                    id=(
                        f"{trade.symbol}-"
                        f"{counter}"
                    ),
                    symbol=trade.symbol,
                    entry_trade=lot.trade,
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

            # ----------------------------------------------
            # Consume the open lot.
            # ----------------------------------------------

            lot.quantity -= close_quantity

            lot.allocated_fees -= entry_fees

            remaining -= close_quantity

            # ----------------------------------------------
            # Lot completely closed.
            # ----------------------------------------------

            if lot.quantity == 0:

                symbol_lots.pop(0)

        # ----------------------------------------------------
        # Excess opposite-side quantity creates a new position.
        #
        # Example:
        #
        # BUY 1
        # SELL 1.5
        #
        # After closing the BUY 1:
        #
        # remaining = 0.5 SELL
        #
        # That 0.5 is a new short lot.
        # ----------------------------------------------------

        if remaining > 0:

            # Only the portion of fees belonging to the
            # newly opened quantity remains attached to
            # the new lot.

            remaining_fee_fraction = (
                remaining
                /
                trade.quantity
            )

            remaining_fees = (
                trade.fees
                *
                remaining_fee_fraction
            )

            symbol_lots.append(
                _OpenLot(
                    trade=trade,
                    quantity=remaining,
                    allocated_fees=remaining_fees,
                )
            )

        # ----------------------------------------------------
        # Remove empty symbol entries.
        # ----------------------------------------------------

        if not symbol_lots:

            del open_lots[
                trade.symbol
            ]

    return tuple(
        closed_trades
    )


# ============================================================
# P&L calculation
# ============================================================


def _calculate_pnl(
    *,
    entry_side: TradeSide,
    entry_price: float,
    exit_price: float,
    quantity: float,
) -> float:
    """
    Calculate gross realized P&L for a matched quantity.

    Long
    ----

        BUY @ entry
        SELL @ exit

        P&L = (exit - entry) * quantity


    Short
    -----

        SELL @ entry
        BUY @ exit

        P&L = (entry - exit) * quantity
    """

    if quantity <= 0:
        raise ValueError(
            "P&L quantity must be positive."
        )

    if entry_side is TradeSide.BUY:

        return (
            exit_price
            -
            entry_price
        ) * quantity

    if entry_side is TradeSide.SELL:

        return (
            entry_price
            -
            exit_price
        ) * quantity

    raise ValueError(
        f"Unsupported trade side: {entry_side}"
    )