"""
analysis.data.downloader

Research-grade market data acquisition layer.

Upgrades:
- Multi-provider architecture (extensible)
- Optional API key support (.env compatible)
- Unified raw format output
- JSON + CSV persistence
- Deterministic file naming
- Clean separation of concerns
"""

from __future__ import annotations

import os
import json
import time
import csv
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import requests


# ============================================================
# CONFIG
# ============================================================

BINANCE_BASE_URL = "https://api.binance.com/api/v3/klines"


# ============================================================
# PROVIDER INTERFACE
# ============================================================

class MarketDataProvider(Protocol):
    def fetch(self, config: "DownloadConfig") -> list[list[Any]]:
        ...


# ============================================================
# CONFIG
# ============================================================

@dataclass
class DownloadConfig:
    symbol: str
    interval: str = "1m"
    start_time: int | None = None
    end_time: int | None = None
    limit: int = 1000

    provider: str = "binance"


# ============================================================
# BINANCE PROVIDER (extendable later)
# ============================================================

class BinanceProvider:
    """
    Handles raw Binance OHLCV requests.

    NOTE:
    - No cleaning
    - No transformation
    - Only raw API retrieval
    """

    def __init__(self):
        self.api_key = os.getenv("BINANCE_API_KEY")
        self.secret = os.getenv("BINANCE_SECRET")

    def fetch(self, config: DownloadConfig) -> list[list[Any]]:

        all_data: list[list[Any]] = []
        start = config.start_time

        while True:

            params = {
                "symbol": config.symbol,
                "interval": config.interval,
                "limit": config.limit,
            }

            if start:
                params["startTime"] = start
            if config.end_time:
                params["endTime"] = config.end_time

            headers = {}

            # optional future authenticated endpoints
            if self.api_key:
                headers["X-MBX-APIKEY"] = self.api_key

            response = requests.get(
                BINANCE_BASE_URL,
                params=params,
                headers=headers,
                timeout=10,
            )

            response.raise_for_status()
            batch = response.json()

            if not batch:
                break

            all_data.extend(batch)

            start = batch[-1][0] + 1

            time.sleep(0.15)

            if len(batch) < config.limit:
                break

        return all_data


# ============================================================
# DOWNLOADER CORE
# ============================================================

class MarketDataDownloader:
    """
    Orchestrates data fetching + persistence.

    Responsibilities:
    - choose provider
    - fetch raw data
    - persist JSON + CSV
    - guarantee reproducibility
    """

    def __init__(self, storage_path: str = "analysis/data/raw/candles"):
        self.storage_path = storage_path
        os.makedirs(self.storage_path, exist_ok=True)

        self.providers: dict[str, MarketDataProvider] = {
            "binance": BinanceProvider(),
        }

    # --------------------------------------------------------
    # PUBLIC API
    # --------------------------------------------------------

    def download(self, config: DownloadConfig) -> str:
        """
        Unified download entry point.
        """

        provider = self.providers.get(config.provider)

        if provider is None:
            raise ValueError(f"Unknown provider: {config.provider}")

        raw_data = provider.fetch(config)

        return self._persist_raw(config, raw_data)

    # --------------------------------------------------------
    # PERSISTENCE
    # --------------------------------------------------------

    def _persist_raw(self, config: DownloadConfig, data: list[list[Any]]) -> str:

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        base_name = f"{config.symbol}_{config.interval}_{timestamp}"

        json_path = os.path.join(self.storage_path, f"{base_name}.json")
        csv_path = os.path.join(self.storage_path, f"{base_name}.csv")

        # -------------------------
        # JSON (raw archive)
        # -------------------------
        with open(json_path, "w") as f:
            json.dump(
                {
                    "metadata": {
                        "symbol": config.symbol,
                        "interval": config.interval,
                        "provider": config.provider,
                        "downloaded_at": timestamp,
                    },
                    "data": data,
                },
                f,
                indent=2,
            )

        # -------------------------
        # CSV (analysis friendly)
        # -------------------------
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)

            writer.writerow(
                ["timestamp", "open", "high", "low", "close", "volume"]
            )

            for row in data:
                writer.writerow(
                    [row[0], row[1], row[2], row[3], row[4], row[5]]
                )

        return json_path

    # --------------------------------------------------------
    # EXTENSIBILITY
    # --------------------------------------------------------

    def register_provider(self, name: str, provider: MarketDataProvider) -> None:
        """
        Plug in new APIs without touching core logic.
        """
        self.providers[name] = provider