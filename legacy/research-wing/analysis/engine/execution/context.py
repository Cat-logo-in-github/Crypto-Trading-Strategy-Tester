"""
analysis.engine.execution.context

Execution context adapters.

Provides execution components with a controlled,
read-only view of portfolio state.

Architecture
------------

Strategy
    ↓
Signal
    ↓
BrokerContext
    ↓
Order

The Broker receives context rather than direct ownership
of portfolio state.

The context provides observation only.

It does NOT:
- create orders
- execute orders
- mutate positions
- mutate account state
- apply trades
"""

from __future__ import annotations

from dataclasses import dataclass

from analysis.engine.portfolio import Portfolio


@dataclass(frozen=True, slots=True)
class PortfolioBrokerContext:
    """
    Read-only broker view of current portfolio state.

    This is the adapter between the execution layer and
    the portfolio layer.

    Broker may observe:

    - current equity
    - current cash
    - current prices
    - current position quantities

    Broker cannot use this context to execute trades.

    Parameters
    ----------
    portfolio:
        Current portfolio state.

    prices:
        Current market prices available to the broker.
    """

    portfolio: Portfolio

    prices: dict[str, float]

    # ---------------------------------------------------------
    # Account information
    # ---------------------------------------------------------

    @property
    def equity(self) -> float:
        """
        Current marked-to-market portfolio equity.
        """

        return self.portfolio.equity(
            self.prices
        )

    @property
    def cash(self) -> float:
        """
        Current available cash.
        """

        return self.portfolio.account.cash

    @property
    def available_cash(self) -> float:
        """
        Spendable account cash.
        """

        return self.portfolio.account.available_cash

    # ---------------------------------------------------------
    # Market information
    # ---------------------------------------------------------

    @property
    def price_lookup(self) -> dict[str, float]:
        """
        Current prices available for sizing/execution.

        Returns the price mapping supplied when the context
        was created.
        """

        return self.prices

    def price(
        self,
        symbol: str,
    ) -> float | None:
        """
        Return the current market price for a symbol.
        """

        return self.prices.get(
            symbol
        )

    # ---------------------------------------------------------
    # Position information
    # ---------------------------------------------------------

    def position_quantity(
        self,
        symbol: str,
    ) -> float:
        """
        Return signed current position quantity.

        Positive:
            long

        Negative:
            short

        Zero:
            flat
        """

        return self.portfolio.position_quantity(
            symbol
        )

    def has_position(
        self,
        symbol: str,
    ) -> bool:
        """
        Return whether the portfolio has an open
        position for the symbol.
        """

        return self.portfolio.has_position(
            symbol
        )

    # ---------------------------------------------------------
    # Representation
    # ---------------------------------------------------------

    def __repr__(self) -> str:
        return (
            "PortfolioBrokerContext("
            f"equity={self.equity:.2f}, "
            f"cash={self.cash:.2f}, "
            f"prices={len(self.prices)}"
            ")"
        )