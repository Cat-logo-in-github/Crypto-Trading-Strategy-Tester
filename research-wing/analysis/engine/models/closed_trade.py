"""
analysis.engine.models.closed_trade

Research representation of a completed position lifecycle.

Trade
-----
A Trade represents one execution.

ClosedTrade
-----------
A ClosedTrade represents one completed portion of a position
lifecycle.

Examples
--------

Single entry / single exit:

    BUY 1.0
        ↓
    SELL 1.0
        ↓
    ClosedTrade(quantity=1.0)


Single entry / multiple exits:

    BUY 1.0
        ↓
    SELL 0.25
        ↓
    ClosedTrade(quantity=0.25)

    SELL 0.25
        ↓
    ClosedTrade(quantity=0.25)

    SELL 0.50
        ↓
    ClosedTrade(quantity=0.50)

The three ClosedTrades together represent the complete
position lifecycle.

This object is immutable and belongs to the research layer.

It does not:

- modify Portfolio
- execute trades
- calculate position state
- reconstruct trade history
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from analysis.engine.trade import Trade, TradeSide


@dataclass(frozen=True, slots=True)
class ClosedTrade:
    """
    Completed portion of a position lifecycle.

    A ClosedTrade connects:

        entry execution
              ↓
        exit execution
              ↓
        realized outcome

    Quantity represents the amount closed by this particular
    exit execution.

    Therefore a single entry may legitimately produce
    multiple ClosedTrade objects when the position is exited
    in pieces.
    """

    id: str

    symbol: str

    entry_trade: Trade

    exit_trade: Trade

    quantity: float

    gross_pnl: float

    fees: float = 0.0

    # ---------------------------------------------------------
    # Validation
    # ---------------------------------------------------------

    def __post_init__(self) -> None:
        """Validate immutable closed-trade state."""

        if self.entry_trade.symbol != self.symbol:
            raise ValueError(
                "Entry trade symbol mismatch."
            )

        if self.exit_trade.symbol != self.symbol:
            raise ValueError(
                "Exit trade symbol mismatch."
            )

        if self.entry_trade.side is self.exit_trade.side:
            raise ValueError(
                "Entry and exit trades must have opposite sides."
            )

        if self.quantity <= 0:
            raise ValueError(
                "Closed trade quantity must be positive."
            )

        if self.quantity > self.entry_trade.quantity:
            raise ValueError(
                "Closed quantity cannot exceed entry trade quantity."
            )

        if self.fees < 0:
            raise ValueError(
                "Fees cannot be negative."
            )

    # ---------------------------------------------------------
    # Direction
    # ---------------------------------------------------------

    @property
    def is_long(self) -> bool:
        """
        Whether this lifecycle portion originated from a BUY.
        """

        return (
            self.entry_trade.side is TradeSide.BUY
        )

    @property
    def is_short(self) -> bool:
        """
        Whether this lifecycle portion originated from a SELL.
        """

        return (
            self.entry_trade.side is TradeSide.SELL
        )

    @property
    def direction(self) -> str:
        """Human-readable position direction."""

        return (
            "LONG"
            if self.is_long
            else "SHORT"
        )

    # ---------------------------------------------------------
    # Execution information
    # ---------------------------------------------------------

    @property
    def entry_time(self) -> datetime:
        """Timestamp of the opening execution."""

        return self.entry_trade.timestamp

    @property
    def exit_time(self) -> datetime:
        """Timestamp of the closing execution."""

        return self.exit_trade.timestamp

    @property
    def entry_price(self) -> float:
        """Average entry price for this lifecycle."""

        return self.entry_trade.price

    @property
    def exit_price(self) -> float:
        """Exit execution price."""

        return self.exit_trade.price

    # ---------------------------------------------------------
    # Holding period
    # ---------------------------------------------------------

    @property
    def holding_period(self) -> timedelta:
        """
        Time between entry and exit.

        The engine uses datetime timestamps, so the research
        layer exposes a normalized timedelta.
        """

        return (
            self.exit_time
            - self.entry_time
        )

    # ---------------------------------------------------------
    # Performance
    # ---------------------------------------------------------

    @property
    def net_pnl(self) -> float:
        """
        Realized P&L after fees.
        """

        return (
            self.gross_pnl
            - self.fees
        )

    @property
    def entry_value(self) -> float:
        """
        Gross capital represented by this closed portion.
        """

        return (
            self.quantity
            * self.entry_price
        )

    @property
    def exit_value(self) -> float:
        """
        Gross exit value represented by this closed portion.
        """

        return (
            self.quantity
            * self.exit_price
        )

    @property
    def return_pct(self) -> float:
        """
        Percentage return relative to entry capital.
        """

        if self.entry_value == 0:
            return 0.0

        return (
            self.net_pnl
            /
            self.entry_value
            *
            100.0
        )

    # ---------------------------------------------------------
    # Outcome
    # ---------------------------------------------------------

    @property
    def is_winner(self) -> bool:
        """Whether this closed portion made money."""

        return self.net_pnl > 0

    @property
    def is_loser(self) -> bool:
        """Whether this closed portion lost money."""

        return self.net_pnl < 0

    @property
    def is_flat(self) -> bool:
        """Whether this closed portion broke even."""

        return self.net_pnl == 0

    # ---------------------------------------------------------
    # Representation
    # ---------------------------------------------------------

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
            f"{self.direction}, "
            f"{outcome}, "
            f"qty={self.quantity}, "
            f"pnl={self.net_pnl:.2f}"
            ")"
        )