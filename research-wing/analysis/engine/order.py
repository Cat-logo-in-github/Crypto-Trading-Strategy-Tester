"""
analysis.engine.order

Order model.

Orders are executable instructions created by the Broker.

A Strategy creates Signals.
A Broker converts Signals into Orders.
"""


from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


class OrderSide(Enum):
    """
    Exchange-level transaction direction.
    """

    BUY = auto()
    SELL = auto()



class OrderType(Enum):
    """
    Execution style.
    """

    MARKET = auto()
    LIMIT = auto()
    STOP = auto()
    STOP_LIMIT = auto()



class OrderStatus(Enum):
    """
    Order lifecycle.
    """

    CREATED = auto()
    SUBMITTED = auto()

    PARTIALLY_FILLED = auto()
    FILLED = auto()

    CANCELLED = auto()
    REJECTED = auto()



@dataclass(slots=True)
class Order:
    """
    Executable trading order.

    Created by Broker.

    Does not represent a completed trade.
    """

    id: str

    timestamp: datetime

    symbol: str

    side: OrderSide

    order_type: OrderType

    quantity: float


    # Limit / stop prices
    limit_price: float | None = None

    stop_price: float | None = None


    # Execution tracking
    filled_quantity: float = 0.0

    average_fill_price: float | None = None


    status: OrderStatus = (
        OrderStatus.CREATED
    )


    fees: float = 0.0


    metadata: dict[str, Any] = field(
        default_factory=dict
    )



    def __post_init__(self) -> None:
        """
        Validate order integrity.
        """

        if self.quantity <= 0:
            raise ValueError(
                "Order quantity must be positive."
            )

        if (
            self.order_type is OrderType.LIMIT
            and self.limit_price is None
        ):
            raise ValueError(
                "LIMIT orders require a limit price."
            )

        if (
            self.order_type is OrderType.STOP
            and self.stop_price is None
        ):
            raise ValueError(
                "STOP orders require a stop price."
            )

        if (
            self.order_type is OrderType.STOP_LIMIT
            and (
                self.limit_price is None
                or self.stop_price is None
            )
        ):
            raise ValueError(
                "STOP_LIMIT orders require both stop and limit prices."
            )


    @property
    def remaining_quantity(self) -> float:
        """
        Quantity still waiting to fill.
        """

        return (
            self.quantity
            -
            self.filled_quantity
        )


    @property
    def filled(self) -> bool:
        return (
            self.status
            is OrderStatus.FILLED
        )


    @property
    def cancelled(self) -> bool:
        return (
            self.status
            is OrderStatus.CANCELLED
        )


    @property
    def rejected(self) -> bool:
        return (
            self.status
            is OrderStatus.REJECTED
        )


    def fill(
        self,
        quantity: float,
        price: float
    ) -> None:
        """
        Register execution.

        Called by execution engine.
        """

        if quantity <= 0:
            raise ValueError(
                "Fill quantity must be positive."
            )

        if quantity > self.remaining_quantity:
            raise ValueError(
                "Cannot fill beyond order quantity."
            )


        previous_value = (
            (self.average_fill_price or 0)
            *
            self.filled_quantity
        )


        new_value = (
            price * quantity
        )


        self.filled_quantity += quantity


        self.average_fill_price = (
            previous_value + new_value
        ) / self.filled_quantity



        if (
            self.filled_quantity
            == self.quantity
        ):
            self.status = (
                OrderStatus.FILLED
            )
        else:
            self.status = (
                OrderStatus.PARTIALLY_FILLED
            )



    def cancel(self) -> None:
        """
        Cancel order.
        """

        if self.filled:
            raise ValueError(
                "Cannot cancel filled order."
            )

        self.status = (
            OrderStatus.CANCELLED
        )


    def reject(self) -> None:
        """
        Reject order.
        """

        self.status = (
            OrderStatus.REJECTED
        )


    def __repr__(self) -> str:

        return (
            "Order("
            f"{self.side.name}, "
            f"{self.symbol}, "
            f"qty={self.quantity}, "
            f"status={self.status.name}"
            ")"
        )