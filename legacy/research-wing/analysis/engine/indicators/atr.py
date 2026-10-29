"""
analysis.engine.indicators.atr

Average True Range (ATR) indicator.

ATR measures market volatility.

Formula:

True Range (TR):

    TR = max(
        high - low,
        abs(high - previous_close),
        abs(low - previous_close)
    )


ATR:

    Wilder's smoothing:

    ATR = (
        previous_ATR * (period - 1)
        + current_TR
    ) / period


ATR does not:
- generate signals
- manage risk
- create orders
- access portfolio state

It only transforms candles into
a volatility measurement.

Used for:
- volatility analysis
- position sizing
- stop-loss calculation
- regime detection
"""

from __future__ import annotations

from collections import deque

from analysis.engine.indicators.base import Indicator
from analysis.engine.models.candle import Candle



class ATR(Indicator):
    """
    Average True Range indicator.

    Uses Wilder's smoothing method,
    which is the standard ATR calculation
    used in technical analysis.

    Parameters
    ----------
    period:
        Number of candles used for ATR calculation.

    Example:

        atr = ATR(period=14)

        atr.update(candle)

        current_volatility = atr.value
    """


    def __init__(
        self,
        period: int = 14,
    ) -> None:

        super().__init__(
            name=f"ATR_{period}"
        )


        if period <= 0:
            raise ValueError(
                "ATR period must be positive."
            )


        self.period = period

        self._tr_values: deque[float] = deque(
            maxlen=period
        )

        self._atr: float | None = None

        self._previous_close: float | None = None



    # --------------------------------------------------
    # Core update
    # --------------------------------------------------

    def update(
        self,
        candle: Candle,
    ) -> None:
        """
        Consume a new candle.

        ATR requires previous close,
        therefore the first candle only
        initializes state.
        """


        if self._previous_close is None:

            true_range = (
                candle.high
                -
                candle.low
            )

        else:

            true_range = max(
                candle.high - candle.low,

                abs(
                    candle.high
                    -
                    self._previous_close
                ),

                abs(
                    candle.low
                    -
                    self._previous_close
                ),
            )


        self._tr_values.append(
            true_range
        )


        # --------------------------------------------------
        # Initial ATR
        # --------------------------------------------------

        if (
            self._atr is None
            and len(self._tr_values) == self.period
        ):

            self._atr = (
                sum(self._tr_values)
                /
                self.period
            )


        # --------------------------------------------------
        # Wilder smoothing
        # --------------------------------------------------

        elif self._atr is not None:

            self._atr = (
                (
                    self._atr
                    *
                    (self.period - 1)
                )
                +
                true_range
            ) / self.period



        self._previous_close = (
            candle.close
        )



    # --------------------------------------------------
    # Value interface
    # --------------------------------------------------

    @property
    def value(
        self,
    ) -> float | None:
        """
        Current ATR value.

        Returns None during warmup.
        """

        return self._atr



    # --------------------------------------------------
    # State management
    # --------------------------------------------------

    def reset(
        self,
    ) -> None:
        """
        Reset indicator state.
        """

        self._tr_values.clear()

        self._atr = None

        self._previous_close = None



    def snapshot(
        self,
    ) -> dict:
        """
        Return ATR-specific state.

        Extends base snapshot for debugging
        and experiment reproducibility.
        """

        state = super().snapshot()

        state.update(
            {
                "period": self.period,
                "previous_close": self._previous_close,
                "samples": len(self._tr_values),
            }
        )

        return state