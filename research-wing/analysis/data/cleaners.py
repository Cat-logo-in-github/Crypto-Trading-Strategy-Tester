"""
analysis.data.cleaners

Research-grade OHLCV validation and normalization layer.

Responsibilities:
- enforce market data integrity rules
- remove corrupted candles
- detect gaps and anomalies
- produce deterministic cleaned dataset
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# ------------------------------------------------------------
# Diagnostics
# ------------------------------------------------------------

@dataclass
class CleanReport:
    """
    Summary of dataset quality after cleaning.
    """

    original_count: int
    cleaned_count: int

    removed_duplicates: int = 0
    removed_invalid_ohlc: int = 0
    removed_negative_volume: int = 0
    detected_gaps: int = 0

    def purity(self) -> float:
        if self.original_count == 0:
            return 0.0
        return self.cleaned_count / self.original_count


# ------------------------------------------------------------
# Cleaner
# ------------------------------------------------------------

class CandleCleaner:
    """
    Validates and sanitizes raw OHLCV data.

    INPUT FORMAT (raw or adapter output):
        {
            "timestamp": int | datetime,
            "open": float,
            "high": float,
            "low": float,
            "close": float,
            "volume": float
        }

    OUTPUT:
        cleaned list[dict]
    """

    def clean(
        self,
        data: list[dict[str, Any]],
        interval_ms: int = 60_000,
        detect_gaps: bool = True
    ) -> tuple[list[dict[str, Any]], CleanReport]:

        if not data:
            return [], CleanReport(0, 0)

        original_count = len(data)

        # ----------------------------------------------------
        # Step 1: normalize timestamps + sort
        # ----------------------------------------------------
        normalized = []
        for d in data:
            normalized.append({
                "timestamp": self._normalize_time(d["timestamp"]),
                "open": float(d["open"]),
                "high": float(d["high"]),
                "low": float(d["low"]),
                "close": float(d["close"]),
                "volume": float(d.get("volume", 0.0)),
            })

        normalized.sort(key=lambda x: x["timestamp"])

        # ----------------------------------------------------
        # Step 2: cleaning loop
        # ----------------------------------------------------
        cleaned = []
        seen = set()

        report = CleanReport(
            original_count=original_count,
            cleaned_count=0,
        )

        prev_ts = None

        for c in normalized:

            ts = c["timestamp"]

            # -------------------------
            # duplicate detection
            # -------------------------
            if ts in seen:
                report.removed_duplicates += 1
                continue
            seen.add(ts)

            # -------------------------
            # volume validation
            # -------------------------
            if c["volume"] < 0:
                report.removed_negative_volume += 1
                continue

            o, h, l, cl = c["open"], c["high"], c["low"], c["close"]

            # -------------------------
            # OHLC integrity rules
            # -------------------------
            if not self._valid_ohlc(o, h, l, cl):
                report.removed_invalid_ohlc += 1
                continue

            # -------------------------
            # gap detection (optional)
            # -------------------------
            if detect_gaps and prev_ts is not None:
                delta = ts - prev_ts

                if delta > interval_ms * 1.5:
                    report.detected_gaps += 1
            prev_ts = ts
            cleaned.append(c)

        report.cleaned_count = len(cleaned)

        return cleaned, report

    # ------------------------------------------------------------
    # Validation rules
    # ------------------------------------------------------------

    def _valid_ohlc(self, o: float, h: float, l: float, c: float) -> bool:
        """
        Strict OHLC validity rules.
        """

        if h < max(o, c, l):
            return False

        if l > min(o, c, h):
            return False

        if h < l:
            return False

        return True

    # ------------------------------------------------------------
    # Time handling
    # ------------------------------------------------------------

    def _normalize_time(self, ts: Any) -> int:
        """
        Convert timestamp into integer milliseconds.
        """

        if isinstance(ts, int):
            return ts

        # datetime support
        try:
            return int(ts.timestamp() * 1000)
        except Exception:
            raise ValueError(f"Invalid timestamp format: {ts}")

    # ------------------------------------------------------------
    # Gap detection (simple but useful baseline)
    # ------------------------------------------------------------

    def _is_gap(self, prev_ts: int, current_ts: int) -> bool:
        """
        Detect missing candles (approximate).

        NOTE:
        This does NOT assume interval here.
        Interval-aware detection will be added in loader layer.
        """

        return (current_ts - prev_ts) > 0