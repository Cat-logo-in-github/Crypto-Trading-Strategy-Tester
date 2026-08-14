"""
analysis.engine.market

Market simulation engine.

The Market is responsible for:
- Providing sequential access to historical candles
- Maintaining simulation time
- Ensuring no look-ahead bias
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence, Optional

from analysis.engine.models.candle import Candle


@dataclass
class Market:
    """
    Sequential market data provider.

    This is NOT a trading engine.
    It is a deterministic iterator over candles.
    """
    symbol: str

    candles: Sequence[Candle]

    index: int = 0

    def __post_init__(self) -> None:

        if not self.symbol:
            raise ValueError(
                "Market requires a symbol."
            )

        if not self.candles:
            raise ValueError(
                "Market requires at least one candle."
            )

        if self.index < 0:
            raise ValueError(
                "Index cannot be negative."
            )

        if self.index >= len(self.candles):
            raise ValueError(
                "Initial index out of range."
            )

    # ---------------------------------------------------------
    # State
    # ---------------------------------------------------------

    @property
    def current(self) -> Candle:
        """
        Current candle in simulation.
        """
        return self.candles[self.index]

    @property
    def timestamp(self):
        return self.current.timestamp

    @property
    def is_last(self) -> bool:
        """
        Whether simulation is at final candle.
        """
        return self.index >= len(self.candles) - 1

    @property
    def has_next(self) -> bool:
        """
        Whether more data exists.
        """
        return self.index < len(self.candles) - 1

    # ---------------------------------------------------------
    # History access (NO lookahead)
    # ---------------------------------------------------------

    def history(self, lookback: Optional[int] = None) -> Sequence[Candle]:
        """
        Returns past candles ONLY (no future leakage).
        """
        if self.index == 0:
            return []

        if lookback is None:
            return self.candles[: self.index]

        if lookback <= 0:
            return []

        start = max(0, self.index - lookback)
        return self.candles[start : self.index]

    # ---------------------------------------------------------
    # Simulation control
    # ---------------------------------------------------------

    def step(self) -> Candle:
        """
        Advance market by one candle.

        Returns the new current candle.
        """
        if self.is_last:
            raise StopIteration("End of market data reached.")

        self.index += 1
        return self.current

    def reset(self) -> None:
        """
        Reset simulation to start.
        """
        self.index = 0

    # ---------------------------------------------------------
    # Convenience helpers
    # ---------------------------------------------------------

    def slice(self, start: int, end: int) -> Sequence[Candle]:
        """
        Safe slice of historical data (absolute indexing).
        """
        return self.candles[start:end]

    def __len__(self) -> int:
        return len(self.candles)

    def __repr__(self) -> str:
        return (
            f"Market("
            f"symbol={self.symbol}, "
            f"index={self.index}, "
            f"current_time={self.current.timestamp}, "
            f"candles={len(self.candles)})"
        )