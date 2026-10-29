"""
analysis.engine.position

Position tracking model.

A Position represents current ownership of an asset.

Trades modify Positions.

Positions are used by Portfolio to calculate:
- exposure
- unrealized PnL
- realized PnL
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from analysis.engine.trade import Trade, TradeSide


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    """
    Immutable historical snapshot of a position.

    Used by research results and reports.

    Unlike Position, this object never changes
    after creation.
    """

    symbol: str

    quantity: float = 0.0

    average_price: float = 0.0

    realized_pnl: float = 0.0

    last_update: datetime | None = None


    @property
    def is_open(self) -> bool:
        """
        Whether the snapshot represents
        an active position.
        """

        return self.quantity != 0


    @property
    def is_long(self) -> bool:
        return self.quantity > 0


    @property
    def is_short(self) -> bool:
        return self.quantity < 0


    def __repr__(self) -> str:

        return (
            "PositionSnapshot("
            f"{self.symbol}, "
            f"qty={self.quantity}, "
            f"avg={self.average_price}"
            ")"
        )



@dataclass(slots=True)
class Position:
    """
    Current asset position.

    Supports:
    - long positions
    - short positions
    - partial exits
    - position flips
    """

    symbol: str


    quantity: float = 0.0

    average_price: float = 0.0


    realized_pnl: float = 0.0


    last_update: datetime | None = None


    # -------------------------------------------------
    # Position state
    # -------------------------------------------------

    @property
    def is_open(self) -> bool:
        """
        Whether position exists.
        """

        return self.quantity != 0


    @property
    def is_long(self) -> bool:
        """
        Long exposure.
        """

        return self.quantity > 0


    @property
    def is_short(self) -> bool:
        """
        Short exposure.
        """

        return self.quantity < 0



    # -------------------------------------------------
    # Market value
    # -------------------------------------------------

    def market_value(
        self,
        price: float
    ) -> float:
        """
        Current position value.

        Short positions produce negative exposure.
        """

        return (
            self.quantity
            *
            price
        )



    def unrealized_pnl(
        self,
        price: float
    ) -> float:
        """
        Profit/loss on open position.

        Long:
            current - entry

        Short:
            entry - current
        """

        if not self.is_open:
            return 0.0


        return (
            price
            -
            self.average_price
        ) * self.quantity



    # -------------------------------------------------
    # Trade updates
    # -------------------------------------------------

    def apply_trade(
        self,
        trade: Trade
    ) -> None:
        """
        Apply executed trade.

        This is the only way a Position changes.
        """


        if trade.symbol != self.symbol:
            raise ValueError(
                "Trade symbol does not match position."
            )


        signed_quantity = self._signed_quantity(
            trade
        )


        # No existing position
        if self.quantity == 0:

            self.quantity = signed_quantity

            self.average_price = (
                trade.price
            )


        # Adding to same direction
        elif self._same_direction(
            signed_quantity
        ):

            self._increase(
                signed_quantity,
                trade.price
            )


        # Reducing or flipping
        else:

            self._decrease_or_flip(
                signed_quantity,
                trade.price
            )


        self.last_update = trade.timestamp



    # -------------------------------------------------
    # Internal helpers
    # -------------------------------------------------

    def _signed_quantity(
        self,
        trade: Trade
    ) -> float:
        """
        Convert trade side into signed quantity.
        """

        if trade.side is TradeSide.BUY:
            return trade.quantity

        return -trade.quantity



    def _same_direction(
        self,
        amount: float
    ) -> bool:
        """
        Check if trade increases exposure.
        """

        return (
            self.quantity > 0
            and amount > 0
        ) or (
            self.quantity < 0
            and amount < 0
        )



    def _increase(
        self,
        amount: float,
        price: float
    ) -> None:
        """
        Add exposure.
        """

        total_value = (
            abs(self.quantity)
            *
            self.average_price
            +
            abs(amount)
            *
            price
        )


        self.quantity += amount


        self.average_price = (
            total_value
            /
            abs(self.quantity)
        )



    def _decrease_or_flip(
        self,
        amount: float,
        price: float
    ) -> None:
        """
        Reduce exposure or reverse direction.
        """

        closing_quantity = min(
            abs(self.quantity),
            abs(amount)
        )


        if self.quantity > 0:

            pnl = (
                price
                -
                self.average_price
            ) * closing_quantity

        else:

            pnl = (
                self.average_price
                -
                price
            ) * closing_quantity


        self.realized_pnl += pnl


        remaining = (
            abs(amount)
            -
            closing_quantity
        )


        # Position fully closed
        if remaining == 0:

            self.quantity = 0

            self.average_price = 0


        # Flip direction
        else:

            if amount > 0:
                self.quantity = remaining
            else:
                self.quantity = -remaining


            self.average_price = price


    def snapshot(self) -> PositionSnapshot:
        """
        Create immutable historical snapshot.

        Used when exporting portfolio state
        outside the simulation engine.
        """

        return PositionSnapshot(
            symbol=self.symbol,
            quantity=self.quantity,
            average_price=self.average_price,
            realized_pnl=self.realized_pnl,
            last_update=self.last_update,
        )


    def __repr__(self) -> str:

        direction = (
            "LONG"
            if self.is_long
            else "SHORT"
            if self.is_short
            else "FLAT"
        )

        return (
            "Position("
            f"{self.symbol}, "
            f"{direction}, "
            f"qty={self.quantity}, "
            f"avg={self.average_price}"
            ")"
        )