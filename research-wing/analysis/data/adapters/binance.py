from typing import Any
from .base import BaseAdapter


class BinanceAdapter(BaseAdapter):
    """
    Adapter for Binance OHLCV API responses.
    """

    def load(self, raw: list[list[Any]]) -> list[dict[str, Any]]:
        """
        Binance format:
        [
            [
                open_time,
                open,
                high,
                low,
                close,
                volume,
                close_time,
                ...
            ]
        ]
        """

        candles = []

        for r in raw:
            candles.append({
                "timestamp": r[0],
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
                "volume": float(r[5]),
            })

        return candles