"""
analysis.engine.indicators.sma

Simple Moving Average indicator.

SMA calculates the arithmetic mean of the closing prices
over a fixed lookback window.

Formula:

    SMA(n) = (P1 + P2 + ... + Pn) / n


Example:

    SMA(5)

    = average of the last 5 closing prices


The indicator:
- consumes candles sequentially
- maintains rolling state
- does not access strategy/portfolio/execution logic
"""

from __future__ import annotations

from collections import deque

from analysis.engine.models.candle import Candle
from analysis.engine.indicators.base import Indicator


class SMA(Indicator):
    """
    Simple Moving Average.

    Parameters
    ----------
    period:
        Number of candles used in calculation.

    Example
    -------

    sma = SMA(period=20)

    sma.update(candle)

    current_value = sma.value
    """

    def __init__(
        self,
        *,
        period: int,
        name: str | None = None,
    ) -> None:

        if period <= 0:
            raise ValueError(
                "SMA period must be positive."
            )

        super().__init__(
            name=name or f"sma_{period}"
        )

        self.period = period

        self._window: deque[float] = deque(
            maxlen=period
        )

        self._sum: float = 0.0

        self._value: float | None = None


    # --------------------------------------------------
    # Indicator update
    # --------------------------------------------------

    def update(
        self,
        candle: Candle,
    ) -> None:
        """
        Add a candle and update SMA value.

        Before enough candles exist:

            value = None

        After warmup:

            value = rolling average close price
        """

        close = candle.close


        # Remove oldest value if window is full
        if len(self._window) == self.period:

            oldest = self._window[0]

            self._sum -= oldest


        self._window.append(
            close
        )

        self._sum += close


        # Warmup period
        if len(self._window) < self.period:

            self._value = None

            return


        self._value = (
            self._sum
            /
            self.period
        )


    # --------------------------------------------------
    # Public value
    # --------------------------------------------------

    @property
    def value(
        self,
    ) -> float | None:

        return self._value


    # --------------------------------------------------
    # State management
    # --------------------------------------------------

    def reset(
        self,
    ) -> None:
        """
        Reset indicator state.
        """

        self._window.clear()

        self._sum = 0.0

        self._value = None


    # --------------------------------------------------
    # Debugging
    # --------------------------------------------------

    def __repr__(self) -> str:

        return (
            "SMA("
            f"period={self.period}, "
            f"value={self.value}"
            ")"
        )