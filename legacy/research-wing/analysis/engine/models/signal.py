"""
analysis.engine.models.signal

Trading signal model.

A Signal represents strategy intent.

IMPORTANT:
A Signal is NOT an order.

Strategies generate Signals.
Brokers translate Signals into executable Orders.

This separation allows different execution models:
- spot markets
- margin
- futures
- crypto
- equities
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any


class SignalAction(Enum):
    """
    High-level trading intent.

    These represent portfolio objectives,
    not exchange actions.
    """

    LONG = auto()
    """
    Increase long exposure.

    Example:
    Buy BTC on spot.
    Buy futures contract.
    Increase existing long position.
    """

    SHORT = auto()
    """
    Increase short exposure.

    Example:
    Short sell equity.
    Open futures short.
    """

    EXIT_LONG = auto()
    """
    Remove long exposure.
    """

    EXIT_SHORT = auto()
    """
    Remove short exposure.
    """

    HOLD = auto()
    """
    No portfolio change.
    """


class PositionSizing(Enum):
    """
    Defines interpretation of quantity.
    """

    UNITS = auto()
    """
    Quantity represents absolute units.

    Example:
    Buy 10 BTC.
    """

    PERCENT_EQUITY = auto()
    """
    Quantity represents percentage of account equity.

    Example:
    Invest 25% of portfolio.
    """

    PERCENT_POSITION = auto()
    """
    Quantity represents percentage of current position.

    Example:
    Close 50% of position.
    """


@dataclass(frozen=True, slots=True)
class Signal:
    """
    Strategy-generated trading decision.

    This object contains:
    - what the strategy wants
    - how strongly it believes it
    - optional risk targets

    It does NOT contain:
    - execution price
    - order type
    - fees
    - slippage
    - fill information
    """

    timestamp: datetime

    symbol: str

    action: SignalAction

    quantity: float = 1.0

    sizing: PositionSizing = PositionSizing.UNITS

    confidence: float = 1.0

    stop_loss: float | None = None

    take_profit: float | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


    def __post_init__(self) -> None:
        """
        Validate signal.
        """

        if not self.symbol:
            raise ValueError(
                "Signal requires a symbol."
            )

        if self.quantity < 0:
            raise ValueError(
                "Quantity cannot be negative."
            )

        if not 0 <= self.confidence <= 1:
            raise ValueError(
                "Confidence must be between 0 and 1."
            )


        if (
            self.stop_loss is not None
            and self.take_profit is not None
            and self.stop_loss == self.take_profit
        ):
            raise ValueError(
                "Stop loss and take profit cannot match."
            )


    # -----------------------------------------------------
    # Intent helpers
    # -----------------------------------------------------

    @property
    def opens_long(self) -> bool:
        """
        True when strategy wants more long exposure.
        """

        return (
            self.action is SignalAction.LONG
        )


    @property
    def opens_short(self) -> bool:
        """
        True when strategy wants more short exposure.
        """

        return (
            self.action is SignalAction.SHORT
        )


    @property
    def closes_long(self) -> bool:
        """
        True when strategy wants to exit long exposure.
        """

        return (
            self.action is SignalAction.EXIT_LONG
        )


    @property
    def closes_short(self) -> bool:
        """
        True when strategy wants to exit short exposure.
        """

        return (
            self.action is SignalAction.EXIT_SHORT
        )


    @property
    def is_hold(self) -> bool:
        return (
            self.action is SignalAction.HOLD
        )


    def __repr__(self) -> str:

        return (
            "Signal("
            f"{self.action.name}, "
            f"{self.symbol}, "
            f"qty={self.quantity}, "
            f"sizing={self.sizing.name}, "
            f"confidence={self.confidence:.2f}"
            ")"
        )