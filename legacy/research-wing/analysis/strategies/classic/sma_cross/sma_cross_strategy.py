"""
analysis.strategies.classic.sma_cross.sma_cross_strategy

Simple moving-average crossover strategy.

Trading rules
-------------

LONG
    Fast SMA crosses above Slow SMA
    while flat.

EXIT_LONG
    Fast SMA crosses below Slow SMA
    while holding a long position.

SHORT
    Fast SMA crosses below Slow SMA
    while flat.

EXIT_SHORT
    Fast SMA crosses above Slow SMA
    while holding a short position.


The strategy only generates Signals.

It does NOT:

- create Orders
- determine execution prices
- calculate fees
- modify Portfolio
- manage Account state


Architecture
------------

    Market
       |
       v
    StrategyContext
       |
       v
    SMACrossoverStrategy
       |
       v
    Signal
       |
       v
    Broker
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

    It explicitly distinguishes:

        LONG
        EXIT_LONG
        SHORT
        EXIT_SHORT

    This prevents a bearish crossover from being incorrectly
    interpreted as a new short entry when the strategy actually
    intends to close a long position.
    """

    name = "SMACrossoverStrategy"

    def __init__(
        self,
        *,
        fast_period: int = 20,
        slow_period: int = 50,
        allocation: float = 100.0,
        allow_short: bool = False,
    ) -> None:

        super().__init__()

        if fast_period <= 0:
            raise ValueError(
                "fast_period must be positive."
            )

        if slow_period <= 0:
            raise ValueError(
                "slow_period must be positive."
            )

        if fast_period >= slow_period:
            raise ValueError(
                "fast_period must be smaller than slow_period."
            )

        if allocation <= 0:
            raise ValueError(
                "allocation must be positive."
            )

        self.fast_period = fast_period
        self.slow_period = slow_period

        self.fast_name = (
            f"sma_{fast_period}"
        )

        self.slow_name = (
            f"sma_{slow_period}"
        )

        self.allocation = allocation

        self.allow_short = allow_short

        self._previous_fast: float | None = None
        self._previous_slow: float | None = None

    # ---------------------------------------------------------
    # Strategy decision
    # ---------------------------------------------------------

    def on(
        self,
        context: StrategyContext,
    ) -> Signal | None:
        """
        Generate a trading signal from the current crossover.

        The strategy observes portfolio state but never mutates it.
        """

        fast = context.indicator(
            self.fast_name
        )

        slow = context.indicator(
            self.slow_name
        )

        # -----------------------------------------------------
        # Indicator warmup
        # -----------------------------------------------------

        if fast is None or slow is None:
            return None

        # -----------------------------------------------------
        # First usable observation
        # -----------------------------------------------------

        if (
            self._previous_fast is None
            or self._previous_slow is None
        ):

            self._previous_fast = fast
            self._previous_slow = slow

            return None

        # -----------------------------------------------------
        # Detect crossover
        # -----------------------------------------------------

        bullish_cross = (
            self._previous_fast
            <= self._previous_slow
            and
            fast
            > slow
        )

        bearish_cross = (
            self._previous_fast
            >= self._previous_slow
            and
            fast
            < slow
        )

        # Update crossover state BEFORE returning.
        self._previous_fast = fast
        self._previous_slow = slow

        # -----------------------------------------------------
        # No crossover
        # -----------------------------------------------------

        if not bullish_cross and not bearish_cross:
            return None

        # -----------------------------------------------------
        # Determine current exposure
        # -----------------------------------------------------

        position = context.positions.get(
            context.symbol
        )

        quantity = (
            position.quantity
            if position is not None
            else 0.0
        )

        is_long = quantity > 0
        is_short = quantity < 0
        is_flat = quantity == 0

        # -----------------------------------------------------
        # Bullish crossover
        # -----------------------------------------------------

        if bullish_cross:

            # -----------------------------------------------
            # Flat -> enter long
            # -----------------------------------------------

            if is_flat:

                return self._signal(
                    context=context,
                    action=SignalAction.LONG,
                )

            # -----------------------------------------------
            # Short -> exit short
            # -----------------------------------------------

            if is_short:

                return self._signal(
                    context=context,
                    action=SignalAction.EXIT_SHORT,
                )

            # -----------------------------------------------
            # Already long
            # -----------------------------------------------

            return None

        # -----------------------------------------------------
        # Bearish crossover
        # -----------------------------------------------------

        if bearish_cross:

            # -----------------------------------------------
            # Long -> exit long
            # -----------------------------------------------

            if is_long:

                return self._signal(
                    context=context,
                    action=SignalAction.EXIT_LONG,
                )

            # -----------------------------------------------
            # Flat -> optionally enter short
            # -----------------------------------------------

            if is_flat and self.allow_short:

                return self._signal(
                    context=context,
                    action=SignalAction.SHORT,
                )

            # -----------------------------------------------
            # Already short
            # -----------------------------------------------

            return None

        return None

    # ---------------------------------------------------------
    # Signal construction
    # ---------------------------------------------------------

    def _signal(
        self,
        *,
        context: StrategyContext,
        action: SignalAction,
    ) -> Signal:
        """
        Construct a strategy Signal.

        Quantity semantics depend on the action:

        LONG / SHORT
            allocation = percentage of equity.

        EXIT_LONG / EXIT_SHORT
            100% of current position.

        The Broker converts these instructions into absolute
        executable quantities.
        """

        if action in (
            SignalAction.EXIT_LONG,
            SignalAction.EXIT_SHORT,
        ):

            sizing = PositionSizing.PERCENT_POSITION
            quantity = 100.0

        else:

            sizing = PositionSizing.PERCENT_EQUITY
            quantity = self.allocation

        return Signal(
            timestamp=context.timestamp,
            symbol=context.symbol,
            action=action,
            quantity=quantity,
            sizing=sizing,
            confidence=1.0,
            metadata={
                "strategy": self.name,
                "fast_period": self.fast_period,
                "slow_period": self.slow_period,
            },
        )