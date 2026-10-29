"""Explicit epoch units and actual market-price mapping, without network fixtures."""

import json
import unittest
from datetime import UTC, datetime, timedelta

from hypothesis_lab.data import load_bars
from hypothesis_lab.features import market_from_dataset, prepare_dataset

JAN_2024 = datetime(2024, 1, 1, tzinfo=UTC)
SECONDS = 1704067200


class ExplicitTimeFormatTests(unittest.TestCase):
    def prepare(self, observed, available, **mapping):
        return prepare_dataset(
            json.dumps([{"observed_at": observed, "available_at": available, "count": 7}]),
            "json",
            {"field_columns": ["count"], **mapping},
        )[0][0]

    def test_seconds_and_milliseconds_are_explicit_independent_utc_units(self):
        for observed_format, observed, available_format, available in (
            ("unix_seconds", SECONDS, "unix_milliseconds", SECONDS * 1000 + 3600000),
            ("unix_milliseconds", SECONDS * 1000, "unix_seconds", SECONDS + 3600),
            ("unix_seconds", str(SECONDS), "iso", "2024-01-01T05:00:00+04:00"),
            ("iso", "2024-01-01T00:00:00Z", "unix_milliseconds", str(SECONDS * 1000 + 3600000)),
        ):
            with self.subTest(observed_format=observed_format, available_format=available_format):
                item = self.prepare(
                    observed,
                    available,
                    timestamp_format=observed_format,
                    available_at_format=available_format,
                    timezone="+04:00",
                )
                self.assertEqual(item.observed_at, JAN_2024)
                self.assertEqual(item.available_at, JAN_2024 + timedelta(hours=1))
                self.assertEqual(item.values, {"count": 7})

    def test_csv_string_epochs_fractional_precision_and_negative_epochs(self):
        items, _ = prepare_dataset(
            "timestamp,published_at,count\n1704067200.125,1704067200250,2\n",
            "csv",
            {"timestamp_format": "unix_seconds", "available_at_format": "unix_milliseconds"},
        )
        self.assertEqual(items[0].observed_at, JAN_2024 + timedelta(milliseconds=125))
        self.assertEqual(items[0].available_at, JAN_2024 + timedelta(milliseconds=250))
        item = self.prepare(
            -1, 0, timestamp_format="unix_seconds", available_at_format="unix_seconds"
        )
        self.assertEqual(item.observed_at, datetime(1969, 12, 31, 23, 59, 59, tzinfo=UTC))
        self.assertEqual(item.available_at, datetime(1970, 1, 1, tzinfo=UTC))

    def test_numeric_timestamps_require_units_and_wrong_selected_units_are_not_guessed(self):
        for mapping in ({}, {"timestamp_format": "unix_seconds"}):
            with self.subTest(mapping=mapping), self.assertRaises(ValueError):
                self.prepare(SECONDS, SECONDS + 3600, **mapping)
        item = self.prepare(
            SECONDS,
            SECONDS,
            timestamp_format="unix_milliseconds",
            available_at_format="unix_milliseconds",
        )
        self.assertEqual(item.observed_at, datetime(1970, 1, 20, 17, 21, 7, 200000, tzinfo=UTC))

    def test_invalid_epoch_values_formats_and_publication_order_reject(self):
        for bad in (True, None, "", "NaN", "inf", "2024-01-01T00:00:00Z", 1e40):
            for key in ("observed_at", "available_at"):
                with self.subTest(bad=bad, key=key), self.assertRaises(ValueError):
                    self.prepare(
                        bad if key == "observed_at" else SECONDS,
                        bad if key == "available_at" else SECONDS + 3600,
                        timestamp_format="unix_seconds",
                        available_at_format="unix_seconds",
                    )
        for key in ("timestamp_format", "available_at_format"):
            for bad in ("auto", "unix", None, [], {}):
                with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                    self.prepare(
                        SECONDS,
                        SECONDS + 3600,
                        **{
                            "timestamp_format": "unix_seconds",
                            "available_at_format": "unix_seconds",
                            key: bad,
                        },
                    )
        with self.assertRaisesRegex(ValueError, "before"):
            self.prepare(
                SECONDS,
                (SECONDS - 1) * 1000,
                timestamp_format="unix_seconds",
                available_at_format="unix_milliseconds",
            )


class MarketMappingTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"t": SECONDS * 1000, "o": 10, "h": 12, "l": 9, "c": 11, "v": 7},
            {"t": (SECONDS + 86400) * 1000, "o": 11, "h": 13, "l": 10, "c": 12, "v": 8},
        ]
        self.mapping = {
            "timestamp_column": "t",
            "timestamp_format": "unix_milliseconds",
            "open": "o",
            "high": "h",
            "low": "l",
            "close": "c",
            "volume": "v",
        }

    def convert(self, rows=None, mapping=None):
        return market_from_dataset(
            json.dumps(self.rows if rows is None else rows),
            "json",
            self.mapping if mapping is None else mapping,
        )

    def test_mapped_json_preserves_actual_ohlcv_and_open_timestamps(self):
        result = self.convert()
        bars = load_bars(result["market_csv"], content=True)
        self.assertEqual(result["rows"], 2)
        self.assertEqual(result["start"], "2024-01-01T00:00:00+00:00")
        self.assertEqual(result["end"], "2024-01-02T00:00:00+00:00")
        self.assertEqual(bars[0].timestamp, JAN_2024)
        self.assertEqual(
            (bars[0].open, bars[0].high, bars[0].low, bars[0].close, bars[0].volume),
            (10, 12, 9, 11, 7),
        )
        self.assertEqual(
            (bars[1].open, bars[1].high, bars[1].low, bars[1].close, bars[1].volume),
            (11, 13, 10, 12, 8),
        )
        self.assertTrue(any("completed intervals" in warning for warning in result["warnings"]))

    def test_csv_date_only_timezone_and_unmapped_optional_volume(self):
        result = market_from_dataset(
            "day,opening,highest,lowest,ending\n2024-01-01,10,12,9,11\n2024-01-02,11,13,10,12\n",
            "csv",
            {
                "timestamp_column": "day",
                "timezone": "+04:00",
                "open": "opening",
                "high": "highest",
                "low": "lowest",
                "close": "ending",
                "volume": "",
            },
        )
        bars = load_bars(result["market_csv"], content=True)
        self.assertEqual(bars[0].timestamp, datetime(2023, 12, 31, 20, tzinfo=UTC))
        self.assertEqual([bar.volume for bar in bars], [0, 0])
        standard = [
            {
                "timestamp": (JAN_2024 + timedelta(days=i)).isoformat(),
                "open": 10,
                "high": 12,
                "low": 9,
                "close": 11,
            }
            for i in range(2)
        ]
        self.assertEqual(
            [b.volume for b in load_bars(self.convert(standard, {})["market_csv"], content=True)],
            [0, 0],
        )
        with self.assertRaisesRegex(ValueError, "timezone"):
            market_from_dataset(
                "timestamp,open,high,low,close\n2024-01-01,10,12,9,11\n2024-01-02,10,12,9,11\n",
                "csv",
                {},
            )

    def test_json_envelopes_nested_mapping_and_second_epochs(self):
        rows = [
            {"time": SECONDS + 86400 * i, "prices": {"open": 10, "high": 12, "low": 9, "close": 11}}
            for i in range(2)
        ]
        result = market_from_dataset(
            json.dumps({"data": rows}),
            "json",
            {
                "timestamp_column": "time",
                "timestamp_format": "unix_seconds",
                **{name: f"prices.{name}" for name in ("open", "high", "low", "close")},
            },
        )
        self.assertEqual(result["start"], JAN_2024.isoformat())
        self.assertEqual(load_bars(result["market_csv"], content=True)[1].close, 11)

    def test_missing_selected_columns_and_malformed_mapping_reject(self):
        for field in ("t", "o", "h", "l", "c", "v"):
            rows = [dict(row) for row in self.rows]
            del rows[1][field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.convert(rows)
        for field in ("timestamp_column", "open", "high", "low", "close", "volume"):
            for bad in ([], {}, 7, None):
                with self.subTest(field=field, bad=bad), self.assertRaises(ValueError):
                    self.convert(mapping={**self.mapping, field: bad})
        for bad in (None, [], "open"):
            with self.subTest(mapping=bad), self.assertRaises(ValueError):
                market_from_dataset(json.dumps(self.rows), "json", bad)

    def test_invalid_ohlcv_values_and_envelopes_reject_instead_of_filling_prices(self):
        for field, bad in (
            ("o", 0),
            ("c", -1),
            ("h", 10),
            ("l", 11),
            ("v", -1),
            ("o", None),
            ("h", ""),
            ("c", "not-a-price"),
            ("c", "NaN"),
            ("v", "inf"),
            ("o", True),
        ):
            rows = [dict(row) for row in self.rows]
            rows[0][field] = bad
            with self.subTest(field=field, bad=bad), self.assertRaises(ValueError):
                self.convert(rows)

    def test_input_order_duplicates_and_interactive_bar_limit_reject(self):
        for rows in (self.rows[:1], list(reversed(self.rows)), [self.rows[0], self.rows[0]]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.convert(rows)
        rows = [{**self.rows[0], "t": (SECONDS + i * 60) * 1000} for i in range(5001)]
        with self.assertRaisesRegex(ValueError, "5,000"):
            self.convert(rows)


if __name__ == "__main__":
    unittest.main()
