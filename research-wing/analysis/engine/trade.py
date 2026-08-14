"""
analysis.engine.trade

Trade model.

A Trade represents a completed execution.

Trades are historical records and should never change
after creation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto



class TradeSide(Enum):
    """
    Direction of executed trade.
    """

    BUY = auto()
    SELL = auto()



@dataclass(frozen=True, slots=True)
class Trade:
    """
    Completed market execution.

    Trades are generated from filled Orders.

    They represent actual market activity.
    """

    id: str

    order_id: str

    timestamp: datetime

    symbol: str

    side: TradeSide

    quantity: float

    price: float

    fees: float = 0.0


    def __post_init__(self) -> None:
        """
        Validate trade.
        """

        if self.quantity <= 0:
            raise ValueError(
                "Trade quantity must be positive."
            )

        if self.price <= 0:
            raise ValueError(
                "Trade price must be positive."
            )

        if self.fees < 0:
            raise ValueError(
                "Fees cannot be negative."
            )


    @property
    def value(self) -> float:
        """
        Gross trade value.
        """

        return (
            self.quantity
            *
            self.price
        )


    @property
    def net_value(self) -> float:
        """
        Trade value including fees.
        """

        return (
            self.value
            +
            self.fees
        )


    @property
    def is_buy(self) -> bool:
        return (
            self.side
            is TradeSide.BUY
        )


    @property
    def is_sell(self) -> bool:
        return (
            self.side
            is TradeSide.SELL
        )


    def __repr__(self) -> str:
        return (
            "Trade("
            f"{self.side.name}, "
            f"{self.symbol}, "
            f"qty={self.quantity}, "
            f"price={self.price}"
            ")"
        )