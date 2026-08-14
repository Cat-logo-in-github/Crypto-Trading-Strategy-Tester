"""
analysis.engine.execution.broker

Broker converts strategy Signals into executable Orders.

The Broker represents the boundary between:

Strategy intent

and

Execution instructions.


Responsibilities:
- translate SignalAction into OrderSide
- resolve order quantity
- create Orders


The Broker does NOT:
- execute orders
- calculate fills
- calculate fees
- update portfolios
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from analysis.engine.models.signal import (
    Signal,
    SignalAction,
    PositionSizing,
)

from analysis.engine.order import (
    Order,
    OrderSide,
    OrderType,
)



class BrokerContext(Protocol):
    """
    Minimal read-only information required by Broker.

    This avoids coupling Broker directly to Portfolio.

    Any object providing these properties can be used.
    """


    @property
    def equity(self) -> float:
        ...

    def position_quantity(
        self,
        symbol: str,
    ) -> float:
        ...



@dataclass(slots=True)
class SimpleBrokerContext:
    """
    Basic context implementation.

    Useful for tests and simple backtests.
    """

    equity_value: float


    @property
    def equity(self) -> float:

        return self.equity_value



    def position_quantity(
        self,
        symbol: str,
    ) -> float:

        return 0.0



class Broker:
    """
    Converts Signals into Orders.

    Currently supports:
    - MARKET orders
    - unit sizing
    - percentage equity sizing
    - percentage position exits
    """



    def create_order(
        self,
        *,
        signal: Signal,
        context: BrokerContext,
    ) -> Order | None:
        """
        Convert strategy signal into order.

        Returns:
            Order if execution is required.
            None for HOLD/no action.
        """


        if signal.is_hold:
            return None



        side = self._resolve_side(
            signal.action
        )


        if side is None:
            return None



        quantity = self._resolve_quantity(
            signal,
            context,
        )


        if quantity <= 0:
            return None



        return Order(
            id=str(uuid4()),
            timestamp=signal.timestamp,
            symbol=signal.symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=quantity,
            metadata={
                "signal_action": signal.action.name,
                "confidence": signal.confidence,
                **signal.metadata,
            },
        )



    def _resolve_quantity(
        self,
        signal: Signal,
        context: BrokerContext,
    ) -> float:
        """
        Convert strategy sizing into absolute units.
        """


        if signal.sizing is PositionSizing.UNITS:

            return signal.quantity



        if signal.sizing is PositionSizing.PERCENT_EQUITY:

            if context.equity <= 0:
                raise ValueError(
                    "Cannot size order with zero equity."
                )
            price = (
                context.price_lookup.get(
                    signal.symbol
                )
            )
            if price is None or price <= 0:
                raise ValueError(
                    "Missing price for percentage sizing."
                )
            capital = (
                context.equity
                *
                signal.quantity
                /
                100
            )
            return (
                capital
                /
                price
            )


        if signal.sizing is PositionSizing.PERCENT_POSITION:

            current_position = (
                context.position_quantity(
                    signal.symbol
                )
            )


            return (
                current_position
                *
                signal.quantity
            )



        raise ValueError(
            "Unsupported position sizing mode."
        )



    @staticmethod
    def _resolve_side(
        action: SignalAction,
    ) -> OrderSide | None:
        """
        Convert strategy intent into
        exchange transaction direction.
        """

        if action is SignalAction.LONG:

            return OrderSide.BUY



        if action is SignalAction.SHORT:

            return OrderSide.SELL



        if action is SignalAction.EXIT_LONG:

            return OrderSide.SELL



        if action is SignalAction.EXIT_SHORT:

            return OrderSide.BUY



        return None