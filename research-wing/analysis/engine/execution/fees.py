"""
analysis.engine.execution.fees

Fee models used by the execution engine.

Fee calculation is isolated from:
- order creation
- order matching
- portfolio accounting

The execution engine asks a FeeModel:
"Given this execution, what fee applies?"

Fee models do not mutate state.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum, auto



class LiquidityType(Enum):
    """
    Describes whether an execution adds or removes liquidity.

    Many exchanges use different fees for:
    - maker orders
    - taker orders
    """

    MAKER = auto()
    TAKER = auto()



class FeeModel(ABC):
    """
    Abstract interface for execution fee calculation.
    """

    @abstractmethod
    def calculate(
        self,
        *,
        price: float,
        quantity: float,
        liquidity: LiquidityType = LiquidityType.TAKER,
    ) -> float:
        """
        Calculate execution fee.

        Parameters
        ----------
        price:
            Execution price.

        quantity:
            Executed quantity.

        liquidity:
            Maker/taker classification.

        Returns
        -------
        float:
            Fee amount in quote currency.
        """
        raise NotImplementedError



class NoFee(FeeModel):
    """
    Zero-cost execution model.

    Useful for:
    - debugging
    - theoretical backtests
    - comparing fee impact
    """

    def calculate(
        self,
        *,
        price: float,
        quantity: float,
        liquidity: LiquidityType = LiquidityType.TAKER,
    ) -> float:

        self._validate(
            price,
            quantity,
        )

        return 0.0



class PercentageFee(FeeModel):
    """
    Percentage-based commission model.

    Example:

        maker_fee = 0.0002
        taker_fee = 0.0005

    Represents:

        fee = execution_value * rate

    """

    def __init__(
        self,
        *,
        maker_rate: float,
        taker_rate: float,
    ) -> None:

        if maker_rate < 0:
            raise ValueError(
                "Maker fee cannot be negative."
            )

        if taker_rate < 0:
            raise ValueError(
                "Taker fee cannot be negative."
            )

        self.maker_rate = maker_rate
        self.taker_rate = taker_rate



    def calculate(
        self,
        *,
        price: float,
        quantity: float,
        liquidity: LiquidityType = LiquidityType.TAKER,
    ) -> float:

        self._validate(
            price,
            quantity,
        )


        rate = (
            self.maker_rate
            if liquidity is LiquidityType.MAKER
            else self.taker_rate
        )


        return (
            price
            *
            quantity
            *
            rate
        )



    @staticmethod
    def _validate(
        price: float,
        quantity: float,
    ) -> None:
        """
        Validate execution inputs.
        """

        if price <= 0:
            raise ValueError(
                "Execution price must be positive."
            )

        if quantity <= 0:
            raise ValueError(
                "Execution quantity must be positive."
            )