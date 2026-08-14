"""
analysis.engine.portfolio

Portfolio model.

Portfolio is the central state container for:

- Account
- Positions
- Trade history

Trades update the portfolio.

Portfolio does not execute trades.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from analysis.engine.account import Account
from analysis.engine.position import Position
from analysis.engine.trade import Trade


@dataclass(slots=True)
class Portfolio:
    """
    Trading portfolio.

    Combines financial state and asset ownership.
    """

    account: Account


    positions: dict[str, Position] = field(
        default_factory=dict
    )


    trades: list[Trade] = field(
        default_factory=list
    )



    def apply_trade(
        self,
        trade: Trade
    ) -> None:
        """
        Apply executed trade.

        This is the only method that mutates
        portfolio state.
        """

        position = (
            self.positions.get(
                trade.symbol
            )
        )


        if position is None:

            position = Position(
                symbol=trade.symbol
            )

            self.positions[
                trade.symbol
            ] = position



        previous_realized = (
            position.realized_pnl
        )


        position.apply_trade(
            trade
        )


        realized_change = (
            position.realized_pnl
            -
            previous_realized
        )


        if realized_change != 0:

            self.account.apply_realized_pnl(
                realized_change
            )


        self.trades.append(
            trade
        )



    # --------------------------------------------------
    # Valuation
    # --------------------------------------------------

    def equity(
        self,
        prices: dict[str, float]
    ) -> float:
        """
        Calculate total portfolio value.

        Cash + unrealized PnL.
        """

        value = (
            self.account.cash
        )


        for symbol, position in self.positions.items():

            price = prices.get(
                symbol
            )

            if price is None:
                continue


            value += (
                position.unrealized_pnl(
                    price
                )
            )


        return value



    def market_value(
        self,
        prices: dict[str, float]
    ) -> float:
        """
        Gross exposure value.
        """

        total = 0.0


        for symbol, position in self.positions.items():

            price = prices.get(
                symbol
            )

            if price is None:
                continue


            total += abs(
                position.market_value(
                    price
                )
            )


        return total



    # --------------------------------------------------
    # Position helpers
    # --------------------------------------------------

    def position(
        self,
        symbol: str
    ) -> Position | None:
        """
        Retrieve position.
        """

        return self.positions.get(
            symbol
        )



    def has_position(
        self,
        symbol: str
    ) -> bool:
        """
        Check open position.
        """

        position = self.position(
            symbol
        )

        return (
            position is not None
            and position.is_open
        )



    def close_position(
        self,
        symbol: str
    ) -> None:
        """
        Remove empty positions.

        Useful after full exits.
        """

        position = self.positions.get(
            symbol
        )


        if (
            position
            and not position.is_open
        ):
            del self.positions[
                symbol
            ]



    def __repr__(self) -> str:

        return (
            "Portfolio("
            f"cash={self.account.cash:.2f}, "
            f"positions={len(self.positions)}, "
            f"trades={len(self.trades)}"
            ")"
        )