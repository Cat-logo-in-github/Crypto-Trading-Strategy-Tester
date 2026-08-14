"""
analysis.engine.indicators.engine

Indicator execution engine.

The IndicatorEngine manages a collection of indicators.

Pipeline:

Candle
   |
   v
IndicatorEngine.update()
   |
   v
Indicators calculate values
   |
   v
StrategyContext.indicators
   |
   v
Strategy


The IndicatorEngine does NOT:
- create signals
- access portfolios
- execute trades
- make strategy decisions

It only manages indicator computation.
"""

from __future__ import annotations

from typing import Iterable, Mapping, Any

from analysis.engine.models.candle import Candle

from analysis.engine.indicators.base import Indicator



class IndicatorEngine:
    """
    Coordinates indicator calculations.

    Example:

        engine = IndicatorEngine(
            [
                SMA(20),
                RSI(14),
                ATR(14),
            ]
        )

        engine.update(candle)

        values = engine.values()


    Result:

        {
            "SMA_20": 102000.5,
            "RSI_14": 55.2,
            "ATR_14": 340.1,
        }
    """


    def __init__(
        self,
        indicators: Iterable[Indicator],
    ) -> None:

        self._indicators: dict[str, Indicator] = {}


        for indicator in indicators:

            self.add(
                indicator
            )



    # --------------------------------------------------
    # Registration
    # --------------------------------------------------

    def add(
        self,
        indicator: Indicator,
    ) -> None:
        """
        Register an indicator.

        Indicator names must be unique because
        they become StrategyContext keys.
        """

        if indicator.name in self._indicators:
            raise ValueError(
                f"Duplicate indicator name: {indicator.name}"
            )


        self._indicators[
            indicator.name
        ] = indicator



    def remove(
        self,
        name: str,
    ) -> None:
        """
        Remove an indicator.
        """

        self._indicators.pop(
            name,
            None,
        )



    # --------------------------------------------------
    # Execution
    # --------------------------------------------------

    def update(
        self,
        candle: Candle,
    ) -> None:
        """
        Feed a new candle into all indicators.

        Must be called once per market step.
        """

        for indicator in self._indicators.values():

            indicator.update(
                candle
            )



    # --------------------------------------------------
    # Access
    # --------------------------------------------------

    def values(
        self,
        *,
        include_unready: bool = False,
    ) -> Mapping[str, Any]:
        """
        Return current indicator values.

        Parameters
        ----------
        include_unready:
            If False, indicators still warming up
            are omitted.

        Example:

            {
                "SMA_20": 100.5,
                "ATR_14": 2.1
            }
        """

        result: dict[str, Any] = {}


        for name, indicator in self._indicators.items():

            if (
                not include_unready
                and not indicator.ready
            ):
                continue


            result[name] = indicator.value


        return result



    def reset(
        self,
    ) -> None:
        """
        Reset all indicators.

        Used before rerunning experiments.
        """

        for indicator in self._indicators.values():

            indicator.reset()



    # --------------------------------------------------
    # Inspection
    # --------------------------------------------------

    @property
    def indicators(
        self,
    ) -> Mapping[str, Indicator]:
        """
        Read-only indicator collection.
        """

        return self._indicators.copy()



    def snapshot(
        self,
    ) -> dict[str, Any]:
        """
        Return complete indicator state.

        Useful for:
        - debugging
        - experiment logging
        - checkpoints
        """

        return {
            name: indicator.snapshot()

            for name, indicator
            in self._indicators.items()
        }



    def __repr__(
        self,
    ) -> str:

        return (
            "IndicatorEngine("
            f"indicators={list(self._indicators.keys())}"
            ")"
        )