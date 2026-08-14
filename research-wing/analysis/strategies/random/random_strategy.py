"""
analysis.strategies.random.random_strategy

Random baseline strategy.

This strategy exists to validate the Research Wing pipeline.

It is intentionally not a profitable strategy.

Uses:
- execution testing
- deterministic debugging
- integration tests
- validating portfolio updates
"""

from __future__ import annotations

import random

from analysis.strategies.base import Strategy

from analysis.engine.models.signal import (
    Signal,
    SignalAction,
)

from analysis.engine.models.context import (
    StrategyContext,
)


class RandomStrategy(Strategy):
    """
    Stochastic baseline strategy.

    Behaviour:

    - Randomly decides whether to trade.
    - Uses simple candle momentum bias.
    - Produces only Signals.

    It does NOT:
    - create Orders
    - execute trades
    - access Portfolio directly
    """

    name = "RandomStrategy"


    def __init__(
        self,
        *,
        seed: int = 42,
        trade_probability: float = 0.3,
    ) -> None:

        super().__init__()

        if not 0 <= trade_probability <= 1:
            raise ValueError(
                "trade_probability must be between 0 and 1."
            )

        self.rng = random.Random(seed)

        self.trade_probability = (
            trade_probability
        )



    def on(
        self,
        context: StrategyContext,
    ) -> Signal | None:
        """
        Generate a trading signal.

        The strategy only expresses intent.
        """

        current = context.current
        previous = context.previous


        # --------------------------------------------------
        # No action
        # --------------------------------------------------

        if (
            self.rng.random()
            >
            self.trade_probability
        ):

            return Signal(
                timestamp=context.timestamp,
                symbol=context.symbol,
                action=SignalAction.HOLD,
                quantity=0.0,
                confidence=0.0,
            )


        # --------------------------------------------------
        # Momentum bias
        # --------------------------------------------------

        if previous is None:

            action = self.rng.choice(
                [
                    SignalAction.LONG,
                    SignalAction.SHORT,
                ]
            )


        elif current.close > previous.close:

            action = SignalAction.LONG


        elif current.close < previous.close:

            action = SignalAction.SHORT


        else:

            action = self.rng.choice(
                [
                    SignalAction.LONG,
                    SignalAction.SHORT,
                ]
            )


        return Signal(
            timestamp=context.timestamp,
            symbol=context.symbol,
            action=action,
            quantity=1.0,
            confidence=0.5,
        )