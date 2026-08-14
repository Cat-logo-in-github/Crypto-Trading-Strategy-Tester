import csv
from datetime import datetime
from typing import Any

from .base import BaseAdapter


class CSVAdapter(BaseAdapter):
    """
    Loads OHLCV data from CSV files.
    """

    def load(self, path: str, timestamp_format: str = "%Y-%m-%d %H:%M:%S") -> list[dict[str, Any]]:
        data = []

        with open(path, "r") as f:
            reader = csv.DictReader(f)

            for row in reader:
                data.append({
                    "timestamp": datetime.strptime(row["timestamp"], timestamp_format),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0)),
                })

        return data