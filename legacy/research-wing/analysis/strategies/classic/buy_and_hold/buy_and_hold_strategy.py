"""
analysis.strategies.classic.buy_and_hold.buy_and_hold_strategy

Buy and Hold investment strategy.

Allocates capital once and maintains
long exposure for the simulation duration.
"""

from __future__ import annotations

from analysis.strategies.base import Strategy

from analysis.engine.models.signal import (
    Signal,
    SignalAction,
    PositionSizing,
)


class BuyAndHoldStrategy(Strategy):
    """
    Passive long-only investment strategy.

    Enters when no position exists.
    Does nothing afterwards.
    """


    def __init__(
        self,
        symbol: str,
    ):
        self.symbol = symbol



    def on(
        self,
        context,
    ) -> Signal | None:
        """
        Generate entry signal if uninvested.
        """


        position = (
            context.positions.get(
                self.symbol
            )
        )


        if (
            position is not None
            and position.is_open
        ):
            return None



        return Signal(
            timestamp=context.timestamp,

            symbol=self.symbol,

            action=SignalAction.LONG,

            quantity=100.0,

            sizing=PositionSizing.PERCENT_EQUITY,
        )