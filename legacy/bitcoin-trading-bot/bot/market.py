"""
market.py

Handles all market data retrieval for the trading bot.
"""

import ccxt
import pandas as pd

from bot.config import (
    EXCHANGE,
    SYMBOL,
    TIMEFRAME,
    OHLCV_LIMIT,
    CANDLE_HISTORY,
)


class MarketData:
    """Fetches market data from a cryptocurrency exchange."""

    def __init__(self):
        self.exchange = self._create_exchange()

    def _create_exchange(self):
        """
        Create and return a CCXT exchange instance.
        """

        exchange_class = getattr(ccxt, EXCHANGE)

        return exchange_class({
            "enableRateLimit": True
        })

    def fetch_ohlcv(self):
        """
        Fetch OHLCV candlestick data.

        Returns
        -------
        pandas.DataFrame
            DataFrame containing:
            timestamp, open, high, low, close, volume
        """

        candles = self.exchange.fetch_ohlcv(
            SYMBOL,
            timeframe=TIMEFRAME,
            limit=OHLCV_LIMIT
        )

        df = pd.DataFrame(
            candles,
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume"
            ]
        )

        df["timestamp"] = pd.to_datetime(
            df["timestamp"],
            unit="ms"
        )

        return df

    def save_candles(self, df):
        """
        Save candles to disk.
        """

        df.to_csv(
            CANDLE_HISTORY, 
            index=False
        )


if __name__ == "__main__":

    market = MarketData()

    df = market.fetch_ohlcv()

    market.save_candles(df)

    print(df.tail())