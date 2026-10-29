"""Independent expectations for reviewed, causal interpretation of real-world tables."""

import json
import unittest
from datetime import UTC, datetime, timedelta

from hypothesis_lab.data import Bar
from hypothesis_lab.features import align_features, inspect_dataset, prepare_dataset, read_records


class AdditionalFormats(unittest.TestCase):
    def test_tsv_and_ndjson_preserve_values_and_reject_ambiguous_rows(self):
        self.assertEqual(read_records("date\tcount\n2024-01-01\t12\n", "tsv")[0]["count"], "12")
        self.assertEqual(read_records('{"x":1}\n\n{"x":2}\n', "ndjson"), [{"x": 1}, {"x": 2}])
        for content, format_name in (
            ("x\tx\n1\t2", "tsv"),
            ('{"x":1,"x":2}', "ndjson"),
            ('{"x":1}\n[2]', "ndjson"),
            ("a\tb\n1\t2\t3", "tsv"),
        ):
            with self.subTest(format=format_name, content=content), self.assertRaises(ValueError):
                read_records(content, format_name)

    def test_geojson_points_expose_coordinates_but_polygon_centroids_are_never_invented(self):
        content = json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"date": "2024-01-01", "count": 3},
                        "geometry": {"type": "Point", "coordinates": [-74, 40.7]},
                    },
                    {
                        "type": "Feature",
                        "properties": {"date": "2024-01-02", "count": 4},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[-74, 40], [-73, 40], [-74, 40]]],
                        },
                    },
                ],
            }
        )
        records = read_records(content, "geojson")
        self.assertEqual((records[0]["_longitude"], records[0]["_latitude"]), (-74, 40.7))
        self.assertNotIn("_longitude", records[1])
        info = inspect_dataset(content, "geojson")
        self.assertEqual(info["interpretation"]["kind"], "geospatial")
        self.assertTrue(any("not converted" in warning for warning in info["warnings"]))
        for coords in ([0, 91], [181, 0], [True, 1], ["0", 1]):
            value = {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"value": 1},
                        "geometry": {"type": "Point", "coordinates": coords},
                    }
                ],
            }
            with self.subTest(coords=coords), self.assertRaises(ValueError):
                read_records(json.dumps(value), "geojson")


class ReviewedMapping(unittest.TestCase):
    def test_airport_panel_offers_series_and_composite_dates(self):
        content = (
            "airport_code,year,month,total\nEWR,2013,Jan,10\nJFK,2013,Jan,30\nEWR,2013,Feb,20\n"
        )
        info = inspect_dataset(content)
        self.assertEqual(info["interpretation"]["entity_candidates"][0]["column"], "airport_code")
        mapping = {
            **info["suggestions"][0]["mapping"],
            "filter": {"column": "airport_code", "equals": "EWR"},
        }
        items, interpreted = prepare_dataset(content, mapping=mapping)
        self.assertEqual(len(items), 2)
        self.assertEqual(
            interpreted["mapping"]["timestamp_parts"], {"year": "year", "month": "month"}
        )
        self.assertEqual([row.observed_at.month for row in items], [2, 3])

    def test_calendar_parts_are_recognized_and_month_is_complete_before_observation(self):
        content = "Year,Month,traffic\n2024,2,10\n2024,3,12\n"
        info = inspect_dataset(content)
        suggestion = info["suggestions"][0]["mapping"]
        self.assertEqual(suggestion["timestamp_parts"], {"year": "Year", "month": "Month"})
        self.assertIn("timezone", " ".join(info["interpretation"]["requires_confirmation"]).lower())
        items, info = prepare_dataset(
            content,
            mapping={
                **suggestion,
                "timezone": "+04:00",
                "availability_mode": "lag",
                "availability_lag_hours": 0,
            },
        )
        self.assertEqual(items[0].observed_at, datetime(2024, 2, 29, 20, tzinfo=UTC))
        self.assertEqual(items[1].observed_at, datetime(2024, 3, 31, 20, tzinfo=UTC))
        self.assertEqual(info["generated_fields"], ["traffic"])
        for bad in (2.5, True, None, 13):
            rows = [{"Year": 2024, "Month": bad, "traffic": 10}]
            with self.subTest(month=bad), self.assertRaises(ValueError):
                prepare_dataset(
                    json.dumps(rows),
                    "json",
                    {**suggestion, "availability_mode": "lag", "availability_lag_hours": 0},
                )

    def test_year_and_year_month_boundaries_are_explicit(self):
        for raw, format_name, expected in (
            (2023, "year", datetime(2024, 1, 1, tzinfo=UTC)),
            ("2024-02", "year_month", datetime(2024, 3, 1, tzinfo=UTC)),
        ):
            content = json.dumps([{"observed_at": raw, "value": 2}])
            items, _ = prepare_dataset(
                content,
                "json",
                {
                    "timestamp_format": format_name,
                    "timezone": "UTC",
                    "availability_mode": "lag",
                    "availability_lag_hours": 0,
                },
            )
            self.assertEqual(items[0].observed_at, expected)
        items, _ = prepare_dataset(
            '[{"Year":2024,"Month":2,"Day":29,"release_year":2024,"release_month":3,"release_day":2,"v":2}]',
            "json",
            {
                "timestamp_parts": {"year": "Year", "month": "Month", "day": "Day"},
                "available_at_parts": {
                    "year": "release_year",
                    "month": "release_month",
                    "day": "release_day",
                },
                "timezone": "UTC",
                "field_columns": ["v"],
            },
        )
        self.assertEqual(items[0].observed_at, datetime(2024, 2, 29, tzinfo=UTC))
        self.assertEqual(items[0].available_at, datetime(2024, 3, 2, tzinfo=UTC))

    def test_ambiguous_calendar_formats_require_a_choice_and_no_timezone_is_assigned(self):
        content = "date,value\n02/03/2024,2\n03/04/2024,3\n"
        info = inspect_dataset(content)
        self.assertTrue(info["quality"]["time_candidates"][0]["ambiguous"])
        self.assertTrue(any("ambiguous" in issue for issue in info["quality"]["issues"]))
        with self.assertRaises(ValueError):
            prepare_dataset(
                content, mapping={"availability_mode": "lag", "availability_lag_hours": 0}
            )
        for format_name, expected in (
            ("date_dmy", datetime(2024, 3, 2, tzinfo=UTC)),
            ("date_mdy", datetime(2024, 2, 3, tzinfo=UTC)),
        ):
            items, _ = prepare_dataset(
                content,
                mapping={
                    "timestamp_format": format_name,
                    "timezone": "UTC",
                    "availability_mode": "lag",
                    "availability_lag_hours": 0,
                },
            )
            self.assertEqual(items[0].observed_at, expected)

    def test_time_and_entity_selections_reconcile_stale_feature_choices_with_explanation(self):
        content = "time,published_at,region,value\n2024-01-01T00:00:00Z,2024-01-01T01:00:00Z,NY,2\n"
        info = inspect_dataset(
            content,
            mapping={
                "timestamp_column": "time",
                "field_columns": ["time", "value"],
                "categorical_columns": ["region", "published_at"],
                "entity_column": "region",
                "text_features": [{"column": "time", "name": "time_text", "operation": "length"}],
            },
        )
        self.assertEqual(info["generated_fields"], ["value"])
        self.assertEqual(info["mapping"]["text_features"], [])
        self.assertTrue(any("Removed time/entity" in warning for warning in info["warnings"]))

    def test_quality_report_and_exact_entity_filter_do_not_silently_mix_regions(self):
        rows = [
            {"date": "2024-01-01", "region": "NY", "sales": 2},
            {"date": "2024-01-01", "region": "NJ", "sales": 100},
            {"date": "2024-01-02", "region": "NY", "sales": None},
        ]
        content = json.dumps(rows)
        info = inspect_dataset(content, "json")
        self.assertEqual(info["interpretation"]["entity_candidates"][0]["values"], ["NY", "NJ"])
        self.assertEqual(info["quality"]["missing_cells"], 1)
        self.assertTrue(info["interpretation"]["requires_confirmation"])
        items, info = prepare_dataset(
            content,
            "json",
            {
                "field_columns": ["sales"],
                "filter": {"column": "region", "equals": "NY"},
                "timezone": "UTC",
                "availability_mode": "lag",
                "availability_lag_hours": 0,
            },
        )
        self.assertEqual([item.values["sales"] for item in items], [2, None])
        self.assertEqual(info["quality"]["selected_rows"], 2)
        with self.assertRaisesRegex(ValueError, "No observations"):
            prepare_dataset(
                content,
                "json",
                {**info["mapping"], "filter": {"column": "region", "equals": "California"}},
            )


class CausalAggregation(unittest.TestCase):
    def test_long_series_aggregate_independently_without_treating_other_series_as_missing(self):
        rows = [
            {
                "observed_at": "2024-01-01T01:00:00Z",
                "available_at": "2024-01-01T01:00:00Z",
                "field": name,
                "value": value,
            }
            for name, value in (("ny_passes", 2), ("nj_passes", 4), ("ny_passes", 3))
        ]
        items, info = prepare_dataset(
            json.dumps(rows),
            "json",
            {
                "aggregation": {
                    "frequency": "day",
                    "operation": "sum",
                    "fields": ["ny_passes", "nj_passes"],
                }
            },
        )
        self.assertEqual(items[0].values, {"ny_passes__sum_day": 5, "nj_passes__sum_day": 4})
        self.assertEqual(info["generated_fields"], ["ny_passes__sum_day", "nj_passes__sum_day"])

    def test_invalid_aggregation_definitions_and_numeric_overflow_reject(self):
        content = '[{"observed_at":"2024-01-01T00:00:00Z","available_at":"2024-01-01T00:00:00Z","value":1}]'
        for aggregation in (
            [],
            {"frequency": "hour", "operation": "count"},
            {"frequency": "day", "operation": "median"},
            {"frequency": "day", "operation": "sum", "fields": []},
            {"frequency": "day", "operation": "sum", "fields": ["missing"]},
        ):
            with self.subTest(aggregation=aggregation), self.assertRaises(ValueError):
                prepare_dataset(content, "json", {"aggregation": aggregation})
        large = '[{"observed_at":"2024-01-01T00:00:00Z","available_at":"2024-01-01T00:00:00Z","value":1e308},{"observed_at":"2024-01-01T01:00:00Z","available_at":"2024-01-01T01:00:00Z","value":1e308}]'
        with self.assertRaisesRegex(ValueError, "finite numeric"):
            prepare_dataset(
                large,
                "json",
                {"aggregation": {"frequency": "day", "operation": "sum", "fields": ["value"]}},
            )

    def test_exact_event_labels_do_not_match_substrings(self):
        rows = [
            {
                "observed_at": f"2024-01-01T0{i}:00:00Z",
                "available_at": f"2024-01-01T0{i}:00:00Z",
                "event": label,
            }
            for i, label in enumerate(["NY", "ny", "NYC", "NJ"])
        ]
        items, _ = prepare_dataset(
            json.dumps(rows),
            "json",
            {
                "field_columns": [],
                "text_features": [
                    {"column": "event", "name": "is_ny", "operation": "equals", "needle": "NY"}
                ],
            },
        )
        self.assertEqual([item.values["is_ny"] for item in items], [1, 1, 0, 0])

    def test_event_counts_are_known_after_bucket_completion_and_latest_publication(self):
        rows = [
            {"observed_at": "2024-01-01T01:00:00Z", "available_at": "2024-01-01T02:00:00Z"},
            {"observed_at": "2024-01-01T03:00:00Z", "available_at": "2024-01-03T00:00:00Z"},
        ]
        items, info = prepare_dataset(
            json.dumps(rows),
            "json",
            {
                "field_columns": [],
                "aggregation": {"frequency": "day", "operation": "count", "fields": []},
            },
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].observed_at, datetime(2024, 1, 2, tzinfo=UTC))
        self.assertEqual(items[0].available_at, datetime(2024, 1, 3, tzinfo=UTC))
        self.assertEqual(items[0].values, {"event_count": 2})
        bars = [
            Bar(datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i), 10, 10, 10, 10)
            for i in range(2)
        ]
        self.assertEqual(
            [row["event_count"] for row in align_features(bars, items, info)], [None, 2]
        )

    def test_sum_mean_missingness_and_no_invented_empty_buckets(self):
        rows = [
            {
                "observed_at": "2024-01-01T01:00:00Z",
                "available_at": "2024-01-01T01:00:00Z",
                "value": 2,
            },
            {
                "observed_at": "2024-01-01T03:00:00Z",
                "available_at": "2024-01-01T03:00:00Z",
                "value": 4,
            },
            {
                "observed_at": "2024-03-01T01:00:00Z",
                "available_at": "2024-03-01T01:00:00Z",
                "value": None,
            },
        ]
        for operation, expected in (("sum", 6), ("mean", 3)):
            items, info = prepare_dataset(
                json.dumps(rows),
                "json",
                {
                    "aggregation": {
                        "frequency": "month",
                        "operation": operation,
                        "fields": ["value"],
                    }
                },
            )
            name = f"value__{operation}_month"
            self.assertEqual(info["generated_fields"], [name])
            self.assertEqual([item.values[name] for item in items], [expected, None])
            self.assertEqual([item.observed_at.month for item in items], [2, 4])

    def test_publication_during_explicit_decision_delay_is_eligible_only_after_delay(self):
        content = '[{"observed_at":"2024-01-01T01:00:00Z","available_at":"2024-01-02T00:00:00.500Z","value":2}]'
        items, info = prepare_dataset(content, "json")
        bars = [Bar(datetime(2024, 1, 1, tzinfo=UTC), 10, 10, 10, 10)]
        self.assertIsNone(align_features(bars, items, info)[0]["value"])
        self.assertEqual(align_features(bars, items, info, decision_delay_seconds=1)[0]["value"], 2)
        for delay in (-1, float("nan"), float("inf")):
            with self.subTest(delay=delay), self.assertRaises(ValueError):
                align_features(bars, items, info, decision_delay_seconds=delay)


if __name__ == "__main__":
    unittest.main()
