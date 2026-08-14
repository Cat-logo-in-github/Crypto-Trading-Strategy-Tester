"""
analysis.engine.indicators.ema

Exponential Moving Average indicator.

EMA assigns exponentially decreasing weights to older prices.

Formula:

    EMA_today =
        Price_today * alpha
        +
        EMA_previous * (1 - alpha)


where:

    alpha = 2 / (period + 1)


Compared with SMA:

SMA:
    - every candle has equal weight
    - slower response

EMA:
    - recent candles matter more
    - faster response


The indicator:
- consumes candles sequentially
- maintains previous EMA state
- does not access strategy/execution/portfolio logic
"""

from __future__ import annotations

from analysis.engine.models.candle import Candle
from analysis.engine.indicators.base import Indicator


class EMA(Indicator):
    """
    Exponential Moving Average.

    Parameters
    ----------
    period:
        Number of candles used for smoothing.

    Example
    -------

    ema = EMA(period=20)

    ema.update(candle)

    current_value = ema.value
    """


    def __init__(
        self,
        *,
        period: int,
        name: str | None = None,
    ) -> None:

        if period <= 0:
            raise ValueError(
                "EMA period must be positive."
            )


        super().__init__(
            name=name or f"ema_{period}"
        )


        self.period = period


        self.alpha = (
            2.0
            /
            (period + 1)
        )


        self._value: float | None = None


        self._warmup_prices: list[float] = []



    # --------------------------------------------------
    # Update
    # --------------------------------------------------

    def update(
        self,
        candle: Candle,
    ) -> None:
        """
        Consume a candle and update EMA.

        Initialization:

        The first EMA value is seeded using SMA
        after enough candles exist.

        This avoids unstable early EMA values.
        """


        close = candle.close


        # ----------------------------------------------
        # Warmup phase
        # ----------------------------------------------

        if self._value is None:

            self._warmup_prices.append(
                close
            )


            if len(self._warmup_prices) < self.period:

                return


            # Seed EMA using SMA
            self._value = (
                sum(self._warmup_prices)
                /
                self.period
            )


            return



        # ----------------------------------------------
        # Recursive EMA update
        # ----------------------------------------------

        self._value = (
            close * self.alpha
            +
            self._value * (1 - self.alpha)
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
        Reset EMA state.
        """

        self._value = None

        self._warmup_prices.clear()



    # --------------------------------------------------
    # Debugging
    # --------------------------------------------------

    def __repr__(self) -> str:

        return (
            "EMA("
            f"period={self.period}, "
            f"value={self.value}"
            ")"
        )