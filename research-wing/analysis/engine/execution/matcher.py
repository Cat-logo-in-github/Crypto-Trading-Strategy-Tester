"""
analysis.engine.execution.matcher

Order execution simulator.

The Matcher converts executable Orders into Trades.

Responsibilities:
- validate order execution possibility
- determine execution timestamp
- determine execution price
- calculate fees
- update order fill state
- create immutable Trade records

The Matcher does NOT:
- create orders
- generate signals
- manage positions
- update portfolios
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from analysis.engine.order import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
)

from analysis.engine.trade import (
    Trade,
    TradeSide,
)

from analysis.engine.execution.fees import (
    FeeModel,
    LiquidityType,
)

from analysis.engine.execution.slippage import (
    SlippageModel,
)

from analysis.engine.execution.latency import (
    LatencyModel,
)



class Matcher:
    """
    Simulated order execution engine.

    Current capabilities:
    - market orders
    - complete fills
    - deterministic execution

    Future:
    - limit matching
    - partial fills
    - market depth
    """



    def __init__(
        self,
        *,
        fee_model: FeeModel,
        slippage_model: SlippageModel,
        latency_model: LatencyModel,
    ) -> None:

        self.fee_model = fee_model
        self.slippage_model = slippage_model
        self.latency_model = latency_model



    def match(
        self,
        *,
        order: Order,
        market_price: float,
        timestamp: datetime,
        liquidity: LiquidityType = LiquidityType.TAKER,
    ) -> Trade | None:
        """
        Execute an order against market conditions.

        Returns:
            Trade if execution succeeds.
            None if order cannot execute.
        """

        self._validate_order(
            order
        )


        if order.status in (
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
        ):
            return None



        if order.order_type is not OrderType.MARKET:
            raise NotImplementedError(
                "Only MARKET orders are supported."
            )



        execution_timestamp = (
            self.latency_model.apply(
                timestamp
            )
        )



        execution_price = (
            self.slippage_model.apply(
                price=market_price,
                quantity=order.quantity,
                side=order.side,
            )
        )



        fees = (
            self.fee_model.calculate(
                price=execution_price,
                quantity=order.quantity,
                liquidity=liquidity,
            )
        )



        order.fill(
            quantity=order.quantity,
            price=execution_price,
        )



        trade = Trade(
            id=str(uuid4()),
            order_id=order.id,
            timestamp=execution_timestamp,
            symbol=order.symbol,
            side=self._trade_side(
                order.side
            ),
            quantity=order.quantity,
            price=execution_price,
            fees=fees,
        )


        return trade



    @staticmethod
    def _trade_side(
        side: OrderSide,
    ) -> TradeSide:
        """
        Convert order direction into trade direction.
        """

        if side is OrderSide.BUY:
            return TradeSide.BUY

        if side is OrderSide.SELL:
            return TradeSide.SELL

        raise ValueError(
            "Unsupported order side."
        )



    @staticmethod
    def _validate_order(
        order: Order,
    ) -> None:
        """
        Validate order before execution.
        """

        if order.quantity <= 0:
            raise ValueError(
                "Order quantity must be positive."
            )

        if not order.symbol:
            raise ValueError(
                "Order requires symbol."
            )