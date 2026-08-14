"""
analysis.engine.execution.context

Execution context adapters.

Provides read-only information required by
execution components such as the Broker.

Execution components receive context objects
instead of direct access to portfolio internals.
"""

from __future__ import annotations

from dataclasses import dataclass

from analysis.engine.portfolio import Portfolio



@dataclass(slots=True)
class PortfolioBrokerContext:
    """
    Read-only broker view of portfolio state.

    Exposes only the information required
    to convert Signals into Orders.

    Broker can access:
    - account equity
    - current positions
    - market prices

    Broker cannot:
    - modify portfolio
    - execute trades
    - update positions
    """

    portfolio: Portfolio

    prices: dict[str, float]


    # --------------------------------------------------
    # Account information
    # --------------------------------------------------

    @property
    def equity(self) -> float:
        """
        Current marked-to-market portfolio value.
        """

        return self.portfolio.equity(
            self.prices
        )


    # --------------------------------------------------
    # Market information
    # --------------------------------------------------

    @property
    def price_lookup(self) -> dict[str, float]:
        """
        Current market prices available
        for execution decisions.
        """

        return self.prices


    # --------------------------------------------------
    # Position information
    # --------------------------------------------------

    def position_quantity(
        self,
        symbol: str,
    ) -> float:
        """
        Current position size.

        Returns zero when no position exists.
        """

        position = (
            self.portfolio.position(
                symbol
            )
        )


        if position is None:
            return 0.0


        return position.quantity