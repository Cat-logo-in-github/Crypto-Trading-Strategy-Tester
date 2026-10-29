"""
analysis.engine.models.context

Strategy execution context.

This object defines the observation boundary between
the simulation engine and strategy logic.

A Strategy receives a StrategyContext and produces
a Signal.

The context represents exactly what a strategy would
know at a specific point in market time.

The context must never contain:
- future candles
- execution information
- broker internals
- pending orders
- mutable engine state
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Sequence

from analysis.engine.models.candle import Candle


@dataclass(frozen=True, slots=True)
class StrategyContext:
    """
    Immutable snapshot of market state available
    to a strategy.

    A new context is created on every market event.

    Strategies should treat this object as read-only.

    The context intentionally separates strategy logic
    from the rest of the engine.

    Strategies can observe:

    - current market data
    - historical candles
    - portfolio state
    - indicator values

    Strategies cannot access:

    - broker execution
    - order lifecycle
    - fills
    - commissions
    - future market data


    Parameters
    ----------
    timestamp:
        Current simulation timestamp.

        This represents the current point in
        the historical market timeline.

    current:
        Current completed candle available to
        the strategy.

    history:
        Historical candles available before the
        current decision.

        This sequence must never contain:
        - the current candle
        - future candles

    portfolio_value:
        Current marked-to-market portfolio value.

    cash:
        Available account cash.

    symbol:
        Trading instrument associated with
        this context.

    positions:
        Current portfolio positions.

        The strategy may inspect positions but
        must not modify them.

    indicators:
        Pre-computed indicator values.

        Examples:

        {
            "sma_50": 42000,
            "rsi_14": 55.2
        }

    metadata:
        Additional optional research information.
    """

    timestamp: datetime

    current: Candle

    history: Sequence[Candle]

    portfolio_value: float

    cash: float

    symbol: str


    positions: Mapping[str, Any] = field(
        default_factory=dict
    )


    indicators: Mapping[str, Any] = field(
        default_factory=dict
    )


    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )



    def __post_init__(self) -> None:
        """
        Validate context integrity.

        Prevents accidental look-ahead bias.
        """

        if self.portfolio_value < 0:
            raise ValueError(
                "Portfolio value cannot be negative."
            )


        if self.cash < 0:
            raise ValueError(
                "Cash cannot be negative."
            )


        if (
            self.history
            and self.history[-1].timestamp
            >= self.current.timestamp
        ):
            raise ValueError(
                "History cannot contain current "
                "or future candles."
            )



    # --------------------------------------------------
    # Market helpers
    # --------------------------------------------------


    @property
    def price(self) -> float:
        """
        Current market price.

        Uses candle close price.

        Strategies should generally use this
        instead of repeatedly accessing:

            context.current.close
        """

        return self.current.close



    @property
    def previous(self) -> Candle | None:
        """
        Previous available candle.

        Returns None during the first
        simulation step.

        Useful for:

        - momentum strategies
        - candle comparisons
        - simple baselines
        """

        if len(self.history) == 0:
            return None

        return self.history[-1]



    def candles(
        self,
        count: int,
    ) -> Sequence[Candle]:
        """
        Return the most recent historical candles.

        The returned candles never include the
        current candle.

        Example:

            context.candles(20)

        can be used for a 20-period indicator.

        Parameters
        ----------
        count:
            Number of historical candles requested.

        Returns
        -------
        Sequence[Candle]:
            Historical candles available to
            the strategy.
        """

        if count <= 0:
            return []

        return self.history[-count:]



    # --------------------------------------------------
    # Indicator helpers
    # --------------------------------------------------


    def indicator(
        self,
        name: str,
        default: Any = None,
    ) -> Any:
        """
        Retrieve an indicator value.

        Example:

            sma = context.indicator(
                "sma_50"
            )

        Parameters
        ----------
        name:
            Indicator identifier.

        default:
            Returned when indicator is unavailable.

        Returns
        -------
        Any:
            Indicator value or default.
        """

        return self.indicators.get(
            name,
            default,
        )



    def has_indicator(
        self,
        name: str,
    ) -> bool:
        """
        Check whether an indicator exists.

        Useful during indicator warmup periods.

        Example:

            if not context.has_indicator(
                "sma_200"
            ):
                return HOLD
        """

        return name in self.indicators



    # --------------------------------------------------
    # Portfolio helpers
    # --------------------------------------------------


    def has_position(
        self,
        symbol: str,
    ) -> bool:
        """
        Check whether an actual open position exists.
        """

        position = self.positions.get(
            symbol
        )

        if position is None:
            return False


        return position.is_open


    def position(
        self,
        symbol: str,
    ) -> Any | None:
        """
        Retrieve a position snapshot.

        Returns None if no position exists.

        Strategies may inspect positions,
        but must not modify them.
        """

        return self.positions.get(
            symbol
        )



    def __repr__(self) -> str:
        return (
            "StrategyContext("
            f"symbol={self.symbol}, "
            f"time={self.timestamp}, "
            f"price={self.current.close}, "
            f"cash={self.cash}, "
            f"value={self.portfolio_value}"
            ")"
        )