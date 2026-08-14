"""
analysis.engine.execution.latency

Latency models used by the execution engine.

Latency represents the delay between:

    strategy decision time

and

    order execution time


Latency models are deterministic transformations.

They do not:
- control simulation time
- sleep
- interact with real clocks
- modify orders
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta



class LatencyModel(ABC):
    """
    Abstract latency model.
    """


    @abstractmethod
    def apply(
        self,
        timestamp: datetime,
    ) -> datetime:
        """
        Calculate execution timestamp.

        Parameters
        ----------
        timestamp:
            Original event timestamp.

        Returns
        -------
        datetime:
            Timestamp after latency delay.
        """

        raise NotImplementedError



class NoLatency(LatencyModel):
    """
    Zero latency execution.

    Useful for:
    - debugging
    - idealized backtests
    """



    def apply(
        self,
        timestamp: datetime,
    ) -> datetime:

        return timestamp



class FixedLatency(LatencyModel):
    """
    Fixed time delay model.

    Example:

        100 milliseconds network latency
    """



    def __init__(
        self,
        *,
        delay: timedelta,
    ) -> None:

        if delay.total_seconds() < 0:
            raise ValueError(
                "Latency cannot be negative."
            )

        self.delay = delay



    def apply(
        self,
        timestamp: datetime,
    ) -> datetime:

        return (
            timestamp
            +
            self.delay
        )



class MillisecondLatency(FixedLatency):
    """
    Convenience latency model.

    Example:

        MillisecondLatency(150)

    represents:

        150ms execution delay
    """



    def __init__(
        self,
        milliseconds: int,
    ) -> None:

        if milliseconds < 0:
            raise ValueError(
                "Milliseconds cannot be negative."
            )


        super().__init__(
            delay=timedelta(
                milliseconds=milliseconds
            )
        )