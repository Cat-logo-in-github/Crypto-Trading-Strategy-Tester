"""
analysis.engine.models.closed_trade

Completed trade analysis model.

A ClosedTrade represents a completed round-trip
position lifecycle.

Unlike Trade:

Trade:
    - represents a single execution event
    - immutable exchange record

ClosedTrade:
    - represents a completed position outcome
    - composed from entry and exit executions
    - used for research analytics

ClosedTrades are immutable historical records.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from analysis.engine.trade import (
    Trade,
    TradeSide,
)


@dataclass(frozen=True, slots=True)
class ClosedTrade:
    """
    Completed position lifecycle.

    Example:

        Entry Trade
              |
              |
        Exit Trade
              |
              v
        ClosedTrade


    Used for:

    - win/loss analysis
    - expectancy
    - profit factor
    - holding time analysis
    - strategy diagnostics
    - visualization
    """

    id: str

    symbol: str

    entry_trade: Trade

    exit_trade: Trade

    quantity: float

    gross_pnl: float

    fees: float


    # -------------------------------------------------
    # Validation
    # -------------------------------------------------

    def __post_init__(self) -> None:
        """
        Validate completed trade.
        """

        if self.entry_trade.symbol != self.symbol:
            raise ValueError(
                "Entry trade symbol mismatch."
            )


        if self.exit_trade.symbol != self.symbol:
            raise ValueError(
                "Exit trade symbol mismatch."
            )


        if self.quantity <= 0:
            raise ValueError(
                "Closed trade quantity must be positive."
            )


        if self.fees < 0:
            raise ValueError(
                "Fees cannot be negative."
            )



    # -------------------------------------------------
    # Direction
    # -------------------------------------------------

    @property
    def is_long(self) -> bool:
        """
        Whether the completed trade was long.
        """

        return (
            self.entry_trade.side
            is TradeSide.BUY
        )


    @property
    def is_short(self) -> bool:
        """
        Whether the completed trade was short.
        """

        return (
            self.entry_trade.side
            is TradeSide.SELL
        )



    # -------------------------------------------------
    # Execution information
    # -------------------------------------------------

    @property
    def entry_time(self) -> datetime | int:
        return self.entry_trade.timestamp


    @property
    def exit_time(self) -> datetime | int:
        return self.exit_trade.timestamp


    @property
    def entry_price(self) -> float:
        return self.entry_trade.price


    @property
    def exit_price(self) -> float:
        return self.exit_trade.price


    @property
    def holding_period(self) -> timedelta:
        """
        Time position was held.

        Supports:
        - datetime timestamps
        - integer millisecond timestamps

        Internal analytics always receive timedelta.
        """

        start = self.entry_time
        end = self.exit_time


        if isinstance(start, datetime) and isinstance(end, datetime):

            return end - start


        if isinstance(start, int) and isinstance(end, int):

            return timedelta(
                milliseconds=end - start
            )


        raise TypeError(
            "Unsupported timestamp type for holding period."
        )


    # -------------------------------------------------
    # Performance
    # -------------------------------------------------

    @property
    def net_pnl(self) -> float:
        """
        Realized PnL after execution costs.
        """

        return (
            self.gross_pnl
            -
            self.fees
        )


    @property
    def return_pct(self) -> float:
        """
        Return relative to entry capital.
        """

        capital = (
            self.quantity
            *
            self.entry_price
        )

        if capital == 0:
            return 0.0


        return (
            self.net_pnl
            /
            capital
        )



    @property
    def is_winner(self) -> bool:
        return self.net_pnl > 0



    @property
    def is_loser(self) -> bool:
        return self.net_pnl < 0



    @property
    def is_flat(self) -> bool:
        return self.net_pnl == 0



    # -------------------------------------------------
    # Representation
    # -------------------------------------------------

    def __repr__(self) -> str:

        outcome = (
            "WIN"
            if self.is_winner
            else "LOSS"
            if self.is_loser
            else "FLAT"
        )


        return (
            "ClosedTrade("
            f"{self.symbol}, "
            f"{outcome}, "
            f"pnl={self.net_pnl:.2f}"
            ")"
        )