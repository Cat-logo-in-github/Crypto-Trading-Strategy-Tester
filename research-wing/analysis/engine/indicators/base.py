"""
analysis.engine.indicators.base

Base indicator architecture.

Indicators transform market data into numerical features
that strategies can consume.

Pipeline:

Candle
   |
   v
Indicator
   |
   v
StrategyContext
   |
   v
Strategy


Indicators:
- do not create signals
- do not access portfolios
- do not execute trades
- do not know about strategies

They only process market information.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from analysis.engine.models.candle import Candle


class Indicator(ABC):
    """
    Abstract base class for all indicators.

    Indicators are stateful because the backtester processes
    candles sequentially.

    Example:

        candle_1 -> update()
        candle_2 -> update()
        candle_3 -> update()

    The indicator maintains internal state and exposes
    its latest calculated value.
    """


    name: str


    def __init__(
        self,
        name: str,
    ) -> None:

        if not name:
            raise ValueError(
                "Indicator name cannot be empty."
            )

        self.name = name


    # --------------------------------------------------
    # Core calculation
    # --------------------------------------------------

    @abstractmethod
    def update(
        self,
        candle: Candle,
    ) -> None:
        """
        Consume a new candle.

        Called once per market step.

        Implementations should:
        - update internal state
        - calculate latest value

        They should NOT:
        - modify candles
        - access portfolio
        - generate signals
        """

        raise NotImplementedError


    @property
    @abstractmethod
    def value(self) -> float | None:
        """
        Current indicator value.

        Returns:

            float
                When enough data exists.

            None
                During warm-up period.
        """

        raise NotImplementedError


    # --------------------------------------------------
    # State helpers
    # --------------------------------------------------

    @property
    def ready(self) -> bool:
        """
        Whether the indicator has a usable value.
        """

        return self.value is not None


    def reset(self) -> None:
        """
        Reset indicator state.

        Useful when running multiple backtests.
        """

        pass


    def snapshot(self) -> dict[str, Any]:
        """
        Return serializable indicator state.

        Useful for:
        - debugging
        - experiment logging
        - checkpointing
        """

        return {
            "name": self.name,
            "value": self.value,
            "ready": self.ready,
        }


    def __repr__(self) -> str:

        return (
            f"{self.__class__.__name__}("
            f"name={self.name}, "
            f"value={self.value}"
            ")"
        )