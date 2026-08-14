"""
indicators.py

Calculates technical indicators used by the trading strategy.
"""

import pandas as pd

from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange

from bot.config import (
    EMA_FAST,
    EMA_SLOW,
    RSI_PERIOD,
    MACD_FAST,
    MACD_SLOW,
    MACD_SIGNAL,
    ATR_PERIOD
)


class IndicatorCalculator:
    """Adds technical indicators to a DataFrame."""

    @staticmethod
    def add_ema(df: pd.DataFrame) -> pd.DataFrame:
        """Add fast and slow EMA columns."""

        df["ema_fast"] = EMAIndicator(
            close=df["close"],
            window=EMA_FAST
        ).ema_indicator()

        df["ema_slow"] = EMAIndicator(
            close=df["close"],
            window=EMA_SLOW
        ).ema_indicator()

        return df

    @staticmethod
    def add_rsi(df: pd.DataFrame) -> pd.DataFrame:
        """Add RSI column."""

        df["rsi"] = RSIIndicator(
            close=df["close"],
            window=RSI_PERIOD
        ).rsi()

        return df
    
    @staticmethod
    def add_atr(df):

        atr = AverageTrueRange(
            high=df["high"],
            low=df["low"],
            close=df["close"],
            window=ATR_PERIOD
        )

        df["atr"] = atr.average_true_range()

        return df

    @staticmethod
    def add_macd(df: pd.DataFrame) -> pd.DataFrame:
        """Add MACD columns."""

        macd = MACD(
            close=df["close"],
            window_fast=MACD_FAST,
            window_slow=MACD_SLOW,
            window_sign=MACD_SIGNAL,
        )

        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        df["macd_histogram"] = macd.macd_diff()

        return df

    @classmethod
    def add_all(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all indicators."""

        df = cls.add_ema(df)
        df = cls.add_rsi(df)
        df = cls.add_macd(df)
        df = cls.add_atr(df)

        return df