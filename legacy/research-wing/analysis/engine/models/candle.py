"""
analysis.engine.models.candle

Canonical OHLCV market data model used throughout the engine.

This module defines the immutable Candle class, representing a single
time interval (bar) of market data.

All engine components (Market, Broker, Indicators, Strategies,
Portfolio valuation, etc.) should use this class rather than raw
dictionaries or pandas rows.

Author:
    Research Wing
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Candle:
    """
    Immutable OHLCV candle.

    Parameters
    ----------
    timestamp : datetime
        Timestamp representing the opening time of the candle.

    open : float
        Opening price.

    high : float
        Highest traded price.

    low : float
        Lowest traded price.

    close : float
        Closing price.

    volume : float
        Trading volume.
    """

    timestamp: datetime

    open: float
    high: float
    low: float
    close: float

    volume: float

    def __post_init__(self) -> None:
        """
        Validate candle integrity.
        """

        if self.high < self.low:
            raise ValueError(
                "High price cannot be lower than low price."
            )

        if self.open < self.low or self.open > self.high:
            raise ValueError(
                "Open price must lie within [low, high]."
            )

        if self.close < self.low or self.close > self.high:
            raise ValueError(
                "Close price must lie within [low, high]."
            )

        if self.volume < 0:
            raise ValueError(
                "Volume cannot be negative."
            )

    # ------------------------------------------------------------------
    # Derived Prices
    # ------------------------------------------------------------------

    @property
    def hl2(self) -> float:
        """
        High-Low midpoint.
        """
        return (self.high + self.low) / 2.0

    @property
    def hlc3(self) -> float:
        """
        Typical Price.
        """
        return (
            self.high +
            self.low +
            self.close
        ) / 3.0

    @property
    def ohlc4(self) -> float:
        """
        Average of OHLC.
        """
        return (
            self.open +
            self.high +
            self.low +
            self.close
        ) / 4.0

    @property
    def weighted_close(self) -> float:
        """
        Weighted Closing Price.
        """
        return (
            self.high +
            self.low +
            (2.0 * self.close)
        ) / 4.0

    @property
    def body(self) -> float:
        """
        Absolute candle body size.
        """
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        """
        Candle range.
        """
        return self.high - self.low

    @property
    def upper_wick(self) -> float:
        """
        Upper shadow length.
        """
        return self.high - max(
            self.open,
            self.close
        )

    @property
    def lower_wick(self) -> float:
        """
        Lower shadow length.
        """
        return min(
            self.open,
            self.close
        ) - self.low

    @property
    def bullish(self) -> bool:
        """
        True if close > open.
        """
        return self.close > self.open

    @property
    def bearish(self) -> bool:
        """
        True if close < open.
        """
        return self.close < self.open

    @property
    def doji(self) -> bool:
        """
        True if candle body is very small
        relative to total range.
        """

        if self.range == 0:
            return True

        return self.body / self.range < 0.1

    # ------------------------------------------------------------------
    # Utility Methods
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """
        Convert candle into dictionary.
        """
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Candle":
        """
        Construct Candle from dictionary.
        """
        return cls(
            timestamp=data["timestamp"],
            open=float(data["open"]),
            high=float(data["high"]),
            low=float(data["low"]),
            close=float(data["close"]),
            volume=float(data["volume"]),
        )

    def __repr__(self) -> str:
        return (
            "Candle("
            f"time={self.timestamp}, "
            f"O={self.open:.2f}, "
            f"H={self.high:.2f}, "
            f"L={self.low:.2f}, "
            f"C={self.close:.2f}, "
            f"V={self.volume:.2f})"
        )