"""
analysis.strategies.classic.sma_cross.sma_cross_strategy

Simple moving average crossover strategy.

Trading rules
-------------

LONG
    Fast SMA crosses above Slow SMA
    and no current position exists.

SHORT
    Fast SMA crosses below Slow SMA
    and a current position exists.

The strategy only generates Signals.
Execution is delegated to the execution engine.
"""

from __future__ import annotations

from analysis.strategies.base import Strategy

from analysis.engine.models.context import (
    StrategyContext,
)

from analysis.engine.models.signal import (
    Signal,
    SignalAction,
    PositionSizing,
)


class SMACrossoverStrategy(Strategy):
    """
    Moving-average crossover strategy.

    The strategy is state-aware.

    It only enters when flat and only exits
    when holding a position.

    This prevents repeated entries during
    prolonged crossover conditions.
    """

    name = "SMACrossoverStrategy"


    def __init__(
        self,
        *,
        fast_period: int = 20,
        slow_period: int = 50,
        allocation: float = 100.0,
    ) -> None:

        super().__init__()


        if fast_period >= slow_period:
            raise ValueError(
                "fast_period must be smaller than slow_period."
            )


        self.fast_name = f"sma_{fast_period}"
        self.slow_name = f"sma_{slow_period}"

        self.allocation = allocation


        self._previous_fast: float | None = None
        self._previous_slow: float | None = None



    def on(
        self,
        context: StrategyContext,
    ) -> Signal | None:
        """
        Generate trading decision.
        """


        fast = context.indicator(
            self.fast_name
        )

        slow = context.indicator(
            self.slow_name
        )


        # Indicator warmup
        if fast is None or slow is None:
            return None



        # First usable observation
        if self._previous_fast is None:

            self._previous_fast = fast
            self._previous_slow = slow

            return None



        has_position = (
            context.has_position(
                context.symbol
            )
        )


        action = SignalAction.HOLD



        #
        # Bullish crossover
        #
        if (
            self._previous_fast <= self._previous_slow
            and
            fast > slow
        ):

            if not has_position:

                action = SignalAction.LONG



        #
        # Bearish crossover
        #
        elif (
            self._previous_fast >= self._previous_slow
            and
            fast < slow
        ):

            if has_position:

                action = SignalAction.SHORT



        self._previous_fast = fast
        self._previous_slow = slow



        if action == SignalAction.HOLD:
            return None



        return Signal(
            timestamp=context.timestamp,

            symbol=context.symbol,

            action=action,

            quantity=self.allocation,

            sizing=PositionSizing.PERCENT_EQUITY,

            confidence=1.0,
        )