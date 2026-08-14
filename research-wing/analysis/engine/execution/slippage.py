"""
analysis.engine.execution.slippage

Slippage models used by the execution engine.

Slippage represents the difference between:

    expected market price

and

    actual execution price


Slippage models do not:
- create orders
- execute trades
- modify portfolios

They only transform prices.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from analysis.engine.order import OrderSide


class SlippageModel(ABC):
    """
    Abstract slippage model.

    Implementations define how execution price
    differs from observed market price.
    """


    @abstractmethod
    def apply(
        self,
        *,
        price: float,
        quantity: float,
        side: OrderSide,
    ) -> float:
        """
        Calculate execution price.

        Parameters
        ----------
        price:
            Current market price.

        quantity:
            Order quantity.

        side:
            BUY or SELL direction.

        Returns
        -------
        float:
            Adjusted execution price.
        """

        raise NotImplementedError
    
    @staticmethod
    def _validate(
        price: float,
        quantity: float,
    ) -> None:
        """
        Validate execution inputs shared by
        all slippage models.
        """

        if price <= 0:
            raise ValueError(
                "Price must be positive."
            )

        if quantity <= 0:
            raise ValueError(
                "Quantity must be positive."
            )


class NoSlippage(SlippageModel):
    """
    Ideal execution model.

    Useful for:
    - debugging
    - baseline comparisons
    """



    def apply(
        self,
        *,
        price: float,
        quantity: float,
        side: OrderSide,
    ) -> float:

        self._validate(
            price,
            quantity,
        )

        return price



class PercentageSlippage(SlippageModel):
    """
    Percentage-based slippage model.

    Example:

        rate = 0.0005

    means:

        5 basis points


    BUY:

        execution_price =
            price * (1 + rate)


    SELL:

        execution_price =
            price * (1 - rate)

    """


    def __init__(
        self,
        *,
        rate: float,
    ) -> None:

        if rate < 0:
            raise ValueError(
                "Slippage rate cannot be negative."
            )

        self.rate = rate



    def apply(
        self,
        *,
        price: float,
        quantity: float,
        side: OrderSide,
    ) -> float:

        self._validate(
            price,
            quantity,
        )


        if side is OrderSide.BUY:

            execution_price = (
                price
                *
                (1 + self.rate)
            )

        elif side is OrderSide.SELL:

            execution_price = (
                price
                *
                (1 - self.rate)
            )

        else:
            raise ValueError(
                "Unsupported order side."
            )


        return execution_price



class FixedBpsSlippage(SlippageModel):
    """
    Basis-point slippage model.

    Example:

        bps = 5

    represents:

        0.05%


    Useful because exchanges often
    describe execution costs in bps.
    """



    def __init__(
        self,
        *,
        basis_points: float,
    ) -> None:

        if basis_points < 0:
            raise ValueError(
                "Basis points cannot be negative."
            )

        self.basis_points = basis_points



    def apply(
        self,
        *,
        price: float,
        quantity: float,
        side: OrderSide,
    ) -> float:

        self._validate(
            price,
            quantity,
        )


        rate = (
            self.basis_points
            /
            10_000
        )


        if side is OrderSide.BUY:

            return price * (
                1 + rate
            )


        if side is OrderSide.SELL:

            return price * (
                1 - rate
            )


        raise ValueError(
            "Unsupported order side."
        )



class LinearImpactSlippage(SlippageModel):
    """
    Simple market impact model.

    Larger orders experience larger slippage.

    Formula:

        impact =
            base_rate * quantity_factor


    This is intentionally simple.

    Future versions may replace this with:
    - volume participation models
    - order book simulation
    - market depth models
    """


    def __init__(
        self,
        *,
        base_rate: float,
        quantity_factor: float,
    ) -> None:

        if base_rate < 0:
            raise ValueError(
                "Base rate cannot be negative."
            )

        if quantity_factor < 0:
            raise ValueError(
                "Quantity factor cannot be negative."
            )

        self.base_rate = base_rate
        self.quantity_factor = quantity_factor



    def apply(
        self,
        *,
        price: float,
        quantity: float,
        side: OrderSide,
    ) -> float:

        self._validate(
            price,
            quantity,
        )


        impact = (
            self.base_rate
            *
            quantity
            *
            self.quantity_factor
        )


        if side is OrderSide.BUY:

            return price * (
                1 + impact
            )


        if side is OrderSide.SELL:

            return price * (
                1 - impact
            )


        raise ValueError(
            "Unsupported order side."
        )
