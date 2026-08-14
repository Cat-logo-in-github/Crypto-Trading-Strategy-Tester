"""
analysis.engine.indicators.rsi

Relative Strength Index indicator.

RSI measures the magnitude of recent price changes
to estimate momentum.

Developed by J. Welles Wilder Jr.


Formula:

    RS = Average Gain / Average Loss


    RSI = 100 - (100 / (1 + RS))


This implementation uses Wilder's smoothing method:

    AvgGain =
        ((Previous AvgGain * (n-1)) + Current Gain) / n


    AvgLoss =
        ((Previous AvgLoss * (n-1)) + Current Loss) / n


The indicator:
- consumes candles sequentially
- maintains internal momentum state
- does not generate signals
- does not access portfolio/execution logic
"""

from __future__ import annotations

from analysis.engine.models.candle import Candle
from analysis.engine.indicators.base import Indicator



class RSI(Indicator):
    """
    Relative Strength Index.

    Parameters
    ----------
    period:
        Number of candles used for calculation.

    Example
    -------

    rsi = RSI(period=14)

    rsi.update(candle)

    current_value = rsi.value
    """


    def __init__(
        self,
        *,
        period: int,
        name: str | None = None,
    ) -> None:

        if period <= 0:
            raise ValueError(
                "RSI period must be positive."
            )


        super().__init__(
            name=name or f"rsi_{period}"
        )


        self.period = period


        self._previous_close: float | None = None


        self._gains: list[float] = []

        self._losses: list[float] = []


        self._average_gain: float | None = None

        self._average_loss: float | None = None


        self._value: float | None = None



    # --------------------------------------------------
    # Update
    # --------------------------------------------------

    def update(
        self,
        candle: Candle,
    ) -> None:
        """
        Consume candle and update RSI.

        Warmup:

        RSI requires:

            period

        price changes before becoming valid.
        """


        close = candle.close


        # First candle cannot produce change
        if self._previous_close is None:

            self._previous_close = close

            return



        change = (
            close
            -
            self._previous_close
        )


        self._previous_close = close


        gain = max(
            change,
            0.0
        )

        loss = max(
            -change,
            0.0
        )


        # ----------------------------------------------
        # Initial accumulation
        # ----------------------------------------------

        if self._average_gain is None:

            self._gains.append(
                gain
            )

            self._losses.append(
                loss
            )


            if len(self._gains) < self.period:

                return



            self._average_gain = (
                sum(self._gains)
                /
                self.period
            )


            self._average_loss = (
                sum(self._losses)
                /
                self.period
            )


        # ----------------------------------------------
        # Wilder smoothing
        # ----------------------------------------------

        else:

            self._average_gain = (
                (
                    self._average_gain
                    *
                    (self.period - 1)
                )
                +
                gain
            ) / self.period



            self._average_loss = (
                (
                    self._average_loss
                    *
                    (self.period - 1)
                )
                +
                loss
            ) / self.period



        self._value = (
            self._calculate_rsi()
        )



    # --------------------------------------------------
    # Calculation
    # --------------------------------------------------

    def _calculate_rsi(
        self,
    ) -> float:

        """
        Calculate RSI from smoothed gains/losses.
        """

        if self._average_loss == 0:

            # No losses means maximum momentum
            return 100.0


        if self._average_gain == 0:

            # No gains means minimum momentum
            return 0.0


        rs = (
            self._average_gain
            /
            self._average_loss
        )


        return (
            100.0
            -
            (
                100.0
                /
                (1.0 + rs)
            )
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
    # Reset
    # --------------------------------------------------

    def reset(
        self,
    ) -> None:
        """
        Reset RSI state.
        """

        self._previous_close = None

        self._gains.clear()

        self._losses.clear()

        self._average_gain = None

        self._average_loss = None

        self._value = None



    # --------------------------------------------------
    # Debugging
    # --------------------------------------------------

    def __repr__(self) -> str:

        return (
            "RSI("
            f"period={self.period}, "
            f"value={self.value}"
            ")"
        )