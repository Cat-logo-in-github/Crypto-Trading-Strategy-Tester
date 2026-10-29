"""Opt-in, read-only public feeds. No exchange order endpoints exist here."""

from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime, timedelta

from .data import Bar, Event, validate_bars


class ProviderError(ValueError):
    pass


def _fetch(url: str) -> dict:
    request = urllib.request.Request(
        url, headers={"User-Agent": "HypothesisLab/0.1 (local research)"}
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ProviderError("Provider response exceeds the supported size")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ProviderError("Provider returned an unexpected response")
        return result
    except urllib.error.HTTPError as error:
        # Never echo URL: it may include a provider key.
        raise ProviderError(
            f"Provider HTTP {error.code}; check provider availability, credentials and quota"
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        raise ProviderError(
            "Provider unavailable or returned invalid data; offline research remains available"
        ) from None


def kraken_snapshot() -> dict:
    data = _fetch("https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=1440")
    if data.get("error"):
        raise ProviderError("Kraken rejected the public data request")
    try:
        result = data.get("result", {})
        keys = [k for k in result if k != "last"]
        if not keys or len(result[keys[0]]) < 3:
            raise ValueError("Not enough completed candles")
        # Kraken ALWAYS includes the current, uncommitted candle as the last row.
        rows = result[keys[0]][:-1]
        bars = validate_bars(
            [
                Bar(
                    datetime.fromtimestamp(float(r[0]), UTC),
                    float(r[1]),
                    float(r[2]),
                    float(r[3]),
                    float(r[4]),
                    float(r[6]),
                )
                for r in rows
            ]
        )
    except (ValueError, TypeError, IndexError, KeyError, OverflowError):
        raise ProviderError("Kraken returned missing or malformed completed candles") from None
    last_close = bars[-1].timestamp + timedelta(days=1)
    now = datetime.now(UTC)
    return {
        "provider": "Kraken public OHLC",
        "kind": "completed_daily_snapshot",
        "status": "connected",
        "fetched_at": now.isoformat(),
        "last_completed_at": last_close.isoformat(),
        "delay_seconds": max(0, (now - last_close).total_seconds()),
        "latest_close": bars[-1].close,
        "bars": [
            {
                "timestamp": b.timestamp.isoformat(),
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            }
            for b in bars
        ],
        "warnings": [
            "Daily completed candles, not a real-time quote. Last uncommitted candle removed.",
            "At most 720 recent candles; availability and usage subject to Kraken terms. Manual refresh; no trading connection.",
        ],
    }


def open_meteo(latitude: float, longitude: float, start: str, end: str) -> dict:
    if (
        not all(math.isfinite(x) for x in (latitude, longitude))
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        raise ValueError("Latitude/longitude are outside valid ranges")
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if not 0 <= (last - first).days <= 366 or first < date(1940, 1, 1):
        raise ValueError("Choose a historical weather range of at most 367 days after 1940")
    if last >= datetime.now(UTC).date() - timedelta(days=5):
        raise ValueError("Archive data requires a historical end date at least six days ago")
    query = urllib.parse.urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start,
            "end_date": end,
            "daily": "temperature_2m_mean",
            "timezone": "UTC",
        }
    )
    data = _fetch("https://archive-api.open-meteo.com/v1/archive?" + query)
    # Reanalysis is revised. Availability is conservatively acquisition time, not invented past release.
    acquired = datetime.now(UTC)
    try:
        daily = data.get("daily", {})
        dates, values = daily.get("time", []), daily.get("temperature_2m_mean", [])
        if not dates or len(dates) != len(values):
            raise ValueError("Missing observations")
        events = [
            Event(
                datetime.fromisoformat(day).replace(tzinfo=UTC) + timedelta(days=1),
                acquired,
                float(value),
                "temperature",
                f"{latitude},{longitude}",
            )
            for day, value in zip(dates, values)
            if value is not None
        ]
        if not events:
            raise ValueError("No observations")
    except (ValueError, TypeError, IndexError, KeyError, AttributeError):
        raise ProviderError("Weather provider returned missing or malformed observations") from None
    return {
        "provider": "Open-Meteo",
        "kind": "revised_historical_reanalysis",
        "attribution": "Weather data by Open-Meteo.com (CC BY 4.0)",
        "events": [
            {
                "observed_at": e.observed_at.isoformat(),
                "available_at": e.available_at.isoformat(),
                "value": e.value,
                "field": e.field,
                "location": e.location,
            }
            for e in events
        ],
        "warnings": [
            "Revised reanalysis is NOT a point-in-time archive. available_at is acquisition time, so these values cannot generate historical trades before acquisition.",
            "Free hosted service is for noncommercial usage and has quotas; see provider terms before use.",
        ],
    }


def alpha_vantage_test(key: str) -> dict:
    query = urllib.parse.urlencode({"function": "GLOBAL_QUOTE", "symbol": "IBM", "apikey": key})
    data = _fetch("https://www.alphavantage.co/query?" + query)
    if data.get("Note") or data.get("Information"):
        raise ProviderError(
            "Provider quota or entitlement limit; standard free allowance is normally 25 calls/day"
        )
    quote = data.get("Global Quote", {})
    try:
        price = float(quote["05. price"])
        if not math.isfinite(price) or price <= 0:
            raise ValueError("Invalid quote")
        trading_day = date.fromisoformat(quote["07. latest trading day"]).isoformat()
    except (ValueError, TypeError, IndexError, KeyError):
        raise ProviderError(
            "No valid quote returned; verify the provider key and service status"
        ) from None
    return {
        "provider": "Alpha Vantage",
        "kind": "end_of_day_snapshot",
        "status": "connected",
        "symbol": "IBM",
        "price": price,
        "latest_trading_day": trading_day,
        "warning": "Standard quote is end-of-day; this is not a real-time feed.",
    }
