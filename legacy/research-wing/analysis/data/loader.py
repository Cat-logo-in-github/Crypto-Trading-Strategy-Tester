"""
analysis.data.loader

Research-grade unified data interface.

This is the ONLY entry point that the engine should use.

Responsibilities:
- dataset orchestration (raw → clean → processed)
- caching for reproducibility
- optional API fetching via downloader
- conversion to Candle objects
"""

from __future__ import annotations

import os
import json
from typing import Any

from analysis.engine.models.candle import Candle

from .downloader import MarketDataDownloader, DownloadConfig
from .cleaners import CandleCleaner, CleanReport


# ------------------------------------------------------------
# Loader
# ------------------------------------------------------------

class DataLoader:
    """
    Unified research-grade dataset interface.

    This class guarantees:
    - reproducible datasets
    - cached processing
    - strict validation
    - engine-safe Candle output
    """

    def __init__(
        self,
        raw_path: str = "analysis/data/raw/candles",
        processed_path: str = "analysis/data/processed",
    ):
        self.raw_path = raw_path
        self.processed_path = processed_path

        os.makedirs(self.raw_path, exist_ok=True)
        os.makedirs(self.processed_path, exist_ok=True)

        self.downloader = MarketDataDownloader()
        self.cleaner = CandleCleaner()

    # --------------------------------------------------------
    # Public API (MAIN ENTRY POINT)
    # --------------------------------------------------------

    def load(
        self,
        symbol: str,
        interval: str = "1m",
        start_time: int | None = None,
        end_time: int | None = None,
        force_download: bool = False,
        use_cache: bool = True,
    ) -> list[Candle]:
        """
        Load dataset end-to-end.

        Flow:
            cache → raw → download → clean → processed → Candle[]
        """

        cache_key = self._build_cache_key(symbol, interval, start_time, end_time)
        processed_file = os.path.join(self.processed_path, f"{cache_key}.json")

        # ----------------------------------------------------
        # Step 1: Load processed cache
        # ----------------------------------------------------
        if use_cache and os.path.exists(processed_file) and not force_download:
            return self._load_processed(processed_file)

        # ----------------------------------------------------
        # Step 2: Load or download raw data
        # ----------------------------------------------------
        raw_data = self._load_or_download(
            symbol,
            interval,
            start_time,
            end_time,
        )

        # ----------------------------------------------------
        # Step 3: Clean dataset
        # ----------------------------------------------------
        cleaned, report = self.cleaner.clean(
            raw_data,
            interval_ms=60_000  # 1m candles
        )

        self._print_report(symbol, report)

        # ----------------------------------------------------
        # Step 4: Convert to Candle objects
        # ----------------------------------------------------
        candles = [
            Candle(
                timestamp=d["timestamp"],
                open=d["open"],
                high=d["high"],
                low=d["low"],
                close=d["close"],
                volume=d["volume"],
            )
            for d in cleaned
        ]

        # ----------------------------------------------------
        # Step 5: Save processed cache
        # ----------------------------------------------------
        self._save_processed(processed_file, candles)

        return candles

    # ------------------------------------------------------------
    # Raw data validity check
    # ------------------------------------------------------------
    def _is_valid_raw(self, path: str) -> bool:
        try:
            if os.path.getsize(path) < 10:
                return False

            with open(path, "r") as f:
                data = json.load(f)

            return (
                isinstance(data, dict)
                and "data" in data
                and len(data["data"]) > 0
            )

        except Exception:
            return False

    # ------------------------------------------------------------
    # Raw data handling
    # ------------------------------------------------------------

    def _load_or_download(
        self,
        symbol: str,
        interval: str,
        start_time: int | None,
        end_time: int | None,
    ) -> list[dict[str, Any]]:

        # 1. Check cache first
        raw_file = self._find_raw_file(symbol, interval)

        if raw_file and self._is_valid_raw(raw_file):
            return self._load_raw(raw_file)

        # 2. Build config FIRST
        config = DownloadConfig(
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
        )

        # 3. Download
        json_path = self.downloader.download(config)

        # 4. Load fresh data
        return self._load_raw(json_path)

    # ------------------------------------------------------------
    # Raw loader
    # ------------------------------------------------------------

    def _load_raw(self, json_path: str) -> list[dict[str, Any]]:
        """
        Load raw dataset from downloader output.
        """

        with open(json_path, "r") as f:
            payload = json.load(f)

        data = payload["data"]

        # Binance format normalization
        return [
            {
                "timestamp": int(r[0]),
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
                "volume": float(r[5]),
            }
            for r in data
        ]

    # ------------------------------------------------------------
    # Processed cache
    # ------------------------------------------------------------

    def _save_processed(self, path: str, candles: list[Candle]) -> None:
        """
        Save processed dataset for deterministic reuse.
        """

        with open(path, "w") as f:
            json.dump(
                [
                    {
                        "timestamp": c.timestamp,
                        "open": c.open,
                        "high": c.high,
                        "low": c.low,
                        "close": c.close,
                        "volume": c.volume,
                    }
                    for c in candles
                ],
                f,
            )

    def _load_processed(self, path: str) -> list[Candle]:
        """
        Load processed dataset directly (fast path).
        """

        with open(path, "r") as f:
            data = json.load(f)

        return [
            Candle(
                timestamp=d["timestamp"],
                open=d["open"],
                high=d["high"],
                low=d["low"],
                close=d["close"],
                volume=d["volume"],
            )
            for d in data
        ]

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------

    def _build_cache_key(
        self,
        symbol: str,
        interval: str,
        start: int | None,
        end: int | None,
    ) -> str:
        return f"{symbol}_{interval}_{start}_{end}"

    def _find_raw_file(self, symbol: str, interval: str) -> str | None:
        """
        Try to reuse existing raw dataset.
        """

        for file in os.listdir(self.raw_path):
            if file.startswith(f"{symbol}_{interval}"):
                return os.path.join(self.raw_path, file)

        return None

    def _print_report(self, symbol: str, report: CleanReport) -> None:
        """
        Minimal research-grade dataset audit log.
        """

        print("\n--- DATA QUALITY REPORT ---")
        print(f"Symbol: {symbol}")
        print(f"Original: {report.original_count}")
        print(f"Cleaned: {report.cleaned_count}")
        print(f"Purity: {report.purity():.4f}")
        print(f"Removed duplicates: {report.removed_duplicates}")
        print(f"Removed invalid OHLC: {report.removed_invalid_ohlc}")
        print(f"Removed negative volume: {report.removed_negative_volume}")
        print(f"Detected gaps: {report.detected_gaps}")
        print("---------------------------\n")