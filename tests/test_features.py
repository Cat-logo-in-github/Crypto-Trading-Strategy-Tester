"""Independent ingestion, knowability and arbitrary-feature research expectations."""

import csv
import hashlib
import io
import json
import math
import unittest
from datetime import UTC, datetime, timedelta

from hypothesis_lab.data import Bar
from hypothesis_lab.features import (
    align_features,
    derive_features,
    inspect_dataset,
    prepare_dataset,
    read_records,
)
from hypothesis_lab.research import rerun_payload, run_experiment

START = datetime(2023, 1, 1, tzinfo=UTC)


def daily_bars(count=5):
    return [Bar(START + timedelta(days=i), 100, 100, 100, 100, 10) for i in range(count)]


def market_csv(count=61, final_close=100):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
    for i in range(count):
        close = final_close if i == count - 1 else 100
        writer.writerow(
            [
                (START + timedelta(days=i)).isoformat(),
                100,
                max(100, close),
                min(100, close),
                close,
                10,
            ]
        )
    return output.getvalue()


def observations(values, field="sales", *, hours=6):
    return [
        {
            "observed_at": (START + timedelta(days=i, hours=hours)).isoformat(),
            "available_at": (START + timedelta(days=i, hours=hours + 3)).isoformat(),
            field: value,
        }
        for i, value in enumerate(values)
    ]


def rule_payload(feature_rows, fields, *, age=24, market_count=61, final_close=100):
    return {
        "mode": "rules",
        "name": "Independent arbitrary-feature fixture",
        "market_csv": market_csv(market_count, final_close),
        "feature_data": json.dumps(feature_rows),
        "feature_format": "json",
        "feature_mapping": {"field_columns": fields, "max_age_hours": age},
        "execution": {"initial_cash": 10000, "fee_bps": 0, "slippage_bps": 0},
        "strategy": {
            "name": "custom",
            "entry": {"left": f"event:{fields[0]}", "op": ">", "right": 0},
            "sizing": "cash",
            "amount": 10,
            "bar_seconds": 86400,
        },
    }


class RecordTests(unittest.TestCase):
    def test_csv_json_nested_arrays_boolean_and_numeric_columns_are_inspected(self):
        content = json.dumps(
            [
                {
                    "timestamp": "2023-01-01T00:00:00Z",
                    "measure": {"traffic": 12},
                    "counts": [1, 2],
                    "open": True,
                    "category": "weekday",
                }
            ]
        )
        rows = read_records(content, "json")
        self.assertEqual(rows[0]["measure.traffic"], 12)
        self.assertEqual(rows[0]["counts.1"], 2)
        info = inspect_dataset(
            content, "json", {"availability_mode": "lag", "availability_lag_hours": 0}
        )
        self.assertIn("open", info["numeric_fields"])
        self.assertIn("category", info["categorical_fields"])
        prepared, _ = prepare_dataset(
            content,
            "json",
            {
                "field_columns": ["measure.traffic", "open"],
                "availability_mode": "lag",
                "availability_lag_hours": 0,
            },
        )
        self.assertEqual(prepared[0].values, {"measure.traffic": 12.0, "open": 1.0})
        for key in ("records", "data", "items"):
            self.assertEqual(read_records(json.dumps({key: [{"x": 2}]}), "json"), [{"x": 2}])
        self.assertEqual(read_records("\ufefftimestamp,x\n2023-01-01T00:00:00Z,3\n")[0]["x"], "3")

    def test_bad_table_shapes_colliding_names_and_nonfinite_data_are_rejected(self):
        bad = [
            ("a,a\n1,2", "csv"),
            (",b\n1,2", "csv"),
            ("a\n1,2", "csv"),
            ("[]", "json"),
            ('[{"x":NaN}]', "json"),
            ('[{"x":1,"x":2}]', "json"),
            ('[{"x":1,"a":{"b":2},"a.b":3}]', "json"),
            ('[{"x":[{}]}]', "json"),
            ('[{"x":1}]', "xml"),
        ]
        for content, format_name in bad:
            with self.subTest(content=content), self.assertRaises(ValueError):
                read_records(content, format_name)
        for value in ("nan", "inf", "-inf"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                inspect_dataset(f"timestamp,x\n2023-01-01T00:00:00Z,{value}\n")
        with self.assertRaises(ValueError):
            read_records(json.dumps([{f"f{i}": i for i in range(101)}]), "json")

    def test_long_form_fields_pivot_independently_and_duplicate_revisions_reject(self):
        content = "observed_at,available_at,field,value\n2023-01-01T00:00:00Z,2023-01-01T01:00:00Z,ice_cream_sales,20\n2023-01-01T00:00:00Z,2023-01-01T01:00:00Z,merch_sales,7\n"
        prepared, info = prepare_dataset(content, mapping={"max_age_hours": 48})
        self.assertEqual(info["generated_fields"], ["ice_cream_sales", "merch_sales"])
        row = align_features(daily_bars(2), prepared, info)[0]
        self.assertEqual(row["ice_cream_sales"], 20)
        self.assertEqual(row["merch_sales"], 7)
        duplicate = content + content.splitlines()[1] + "\n"
        with self.assertRaises(ValueError):
            prepare_dataset(duplicate)
        with self.assertRaises(ValueError):
            prepare_dataset(content.replace("ice_cream_sales,20", ",20"))

    def test_mapping_requires_valid_distinct_types_and_nonempty_output_names(self):
        content = json.dumps(
            [
                {
                    "observed_at": START.isoformat(),
                    "available_at": START.isoformat(),
                    "count": 2,
                    "text": "duck",
                }
            ]
        )
        bad = [
            {"field_columns": ["text"]},
            {"field_columns": ["count", "count"]},
            {"categorical_columns": ["count"]},
            {"field_columns": "count"},
            {
                "field_columns": [],
                "text_features": [{"column": "text", "name": "", "operation": "length"}],
            },
            {
                "field_columns": [],
                "text_features": [
                    {"column": "text", "name": "signal", "operation": "contains", "needle": ""}
                ],
            },
            {
                "field_columns": [],
                "text_features": [
                    {"column": "text", "name": "market.close", "operation": "length"}
                ],
            },
        ]
        for mapping in bad:
            with self.subTest(mapping=mapping), self.assertRaises(ValueError):
                prepare_dataset(content, "json", mapping)

    def test_categorical_hash_is_fixed_and_does_not_learn_future_vocabulary(self):
        rows = observations(["weekday", "weekend", "new unseen category"], "category")
        mapping = {"field_columns": [], "categorical_columns": ["category"]}
        full, full_info = prepare_dataset(json.dumps(rows), "json", mapping)
        prefix, prefix_info = prepare_dataset(json.dumps(rows[:2]), "json", mapping)
        self.assertEqual(full_info["generated_fields"], prefix_info["generated_fields"])
        self.assertEqual([row.values for row in full[:2]], [row.values for row in prefix])
        bucket = int.from_bytes(hashlib.sha256(b"weekday").digest()[:4], "big") % 8
        self.assertEqual(full[0].values[f"category__hash_{bucket}"], 1.0)
        self.assertEqual(sum(full[0].values.values()), 1)
        self.assertTrue(any("collisions" in warning for warning in full_info["warnings"]))

    def test_explicit_text_signals_count_match_and_length_without_interpretation(self):
        rows = observations(["DUCK duck merchant", "ordinary text"], "headline")
        prepared, info = prepare_dataset(
            json.dumps(rows),
            "json",
            {
                "field_columns": [],
                "text_features": [
                    {
                        "column": "headline",
                        "name": "duck_mentions",
                        "operation": "count",
                        "needle": "duck",
                    },
                    {
                        "column": "headline",
                        "name": "mentions_merch",
                        "operation": "contains",
                        "needle": "MERCHANT",
                    },
                    {"column": "headline", "name": "characters", "operation": "length"},
                ],
            },
        )
        self.assertEqual(
            prepared[0].values, {"duck_mentions": 2.0, "mentions_merch": 1.0, "characters": 18.0}
        )
        self.assertEqual(prepared[1].values["duck_mentions"], 0.0)
        self.assertEqual(
            info["generated_fields"], ["duck_mentions", "mentions_merch", "characters"]
        )


class AvailabilityTests(unittest.TestCase):
    def test_naive_dates_require_explicit_timezone_and_offsets_normalize(self):
        content = "date,published_at,x\n2023-01-01,2023-01-01T03:00:00,5\n"
        with self.assertRaises(ValueError):
            prepare_dataset(content)
        prepared, _ = prepare_dataset(content, mapping={"timezone": "UTC"})
        self.assertEqual(prepared[0].observed_at, START)
        prepared, _ = prepare_dataset(content, mapping={"timezone": "+04:00"})
        self.assertEqual(prepared[0].observed_at, START - timedelta(hours=4))
        for timezone in ("local", "+25:00", "+-1:00", "+04:75"):
            with self.subTest(timezone=timezone), self.assertRaises(ValueError):
                prepare_dataset(content, mapping={"timezone": timezone})
        explicit = (
            "observed_at,available_at,x\n2023-01-01T04:00:00+04:00,2023-01-01T05:00:00+04:00,5\n"
        )
        prepared, _ = prepare_dataset(explicit)
        self.assertEqual(prepared[0].observed_at, START)

    def test_unknown_publication_defaults_to_acquisition_not_historical_eligibility(self):
        content = "timestamp,sales\n2023-01-01T00:00:00Z,10\n"
        prepared, info = prepare_dataset(content, mapping={"acquired_at": "2030-01-01T00:00:00Z"})
        self.assertEqual(info["mapping"]["availability_mode"], "acquired")
        self.assertTrue(
            all(row["sales"] is None for row in align_features(daily_bars(3), prepared, info))
        )
        prepared, info = prepare_dataset(
            content,
            mapping={"availability_mode": "lag", "availability_lag_hours": 30, "max_age_hours": 72},
        )
        aligned = align_features(daily_bars(3), prepared, info)
        self.assertIsNone(aligned[0]["sales"])
        self.assertEqual(aligned[1]["sales"], 10)
        self.assertTrue(any("Exploratory" in warning for warning in info["warnings"]))

    def test_revisions_wait_for_publication_and_never_replace_newer_observation(self):
        rows = [
            {"observed_at": START.isoformat(), "available_at": START.isoformat(), "sales": 1},
            {
                "observed_at": (START + timedelta(days=1)).isoformat(),
                "available_at": (START + timedelta(days=1)).isoformat(),
                "sales": 2,
            },
            {
                "observed_at": START.isoformat(),
                "available_at": (START + timedelta(days=2)).isoformat(),
                "sales": 999,
            },
        ]
        prepared, info = prepare_dataset(json.dumps(rows), "json", {"max_age_hours": 48})
        aligned = align_features(daily_bars(5), prepared, info, bar_seconds=3600)
        self.assertEqual([row["sales"] for row in aligned], [1, 2, 2, None, None])
        future = {
            "observed_at": (START + timedelta(days=3)).isoformat(),
            "available_at": (START + timedelta(days=10)).isoformat(),
            "sales": -1000,
        }
        full, full_info = prepare_dataset(
            json.dumps(rows + [future]), "json", {"max_age_hours": 48}
        )
        self.assertEqual(align_features(daily_bars(3), full, full_info, 3600), aligned[:3])

    def test_newer_missing_observation_is_missing_and_expiry_boundary_is_explicit(self):
        prepared, info = prepare_dataset(
            json.dumps(observations([10, None])), "json", {"max_age_hours": 48}
        )
        rows = align_features(daily_bars(3), prepared, info)
        self.assertEqual(rows[0]["sales"], 10)
        self.assertIsNone(rows[1]["sales"])
        self.assertIsNone(rows[2]["sales"])
        one, one_info = prepare_dataset(
            json.dumps(
                [{"observed_at": START.isoformat(), "available_at": START.isoformat(), "sales": 7}]
            ),
            "json",
            {"max_age_hours": 48},
        )
        self.assertEqual(
            [row["sales"] for row in align_features(daily_bars(3), one, one_info)], [7, 7, None]
        )

    def test_invalid_availability_expiry_and_duplicate_keys_fail(self):
        row = {
            "observed_at": START.isoformat(),
            "available_at": (START - timedelta(seconds=1)).isoformat(),
            "sales": 7,
        }
        with self.assertRaises(ValueError):
            prepare_dataset(json.dumps([row]), "json")
        row["available_at"] = START.isoformat()
        with self.assertRaises(ValueError):
            prepare_dataset(json.dumps([row, row]), "json")
        for age in (0, -1, float("nan"), float("inf")):
            with self.subTest(age=age), self.assertRaises(ValueError):
                prepare_dataset(json.dumps([row]), "json", {"max_age_hours": age})
        for lag in (-1, float("inf"), 87601):
            with self.subTest(lag=lag), self.assertRaises(ValueError):
                prepare_dataset(
                    json.dumps([row]),
                    "json",
                    {"availability_mode": "lag", "availability_lag_hours": lag},
                )


class TransformTests(unittest.TestCase):
    def test_hand_calculated_lag_change_and_trailing_statistics(self):
        values = [{"x": x} for x in [1.0, 2.0, 4.0, None, 8.0]]
        definitions = [
            {
                "source": "x",
                "name": operation,
                "operation": operation,
                "window": 1 if operation in {"lag", "difference", "pct_change"} else 2,
            }
            for operation in ("lag", "difference", "pct_change", "mean", "sum", "zscore")
        ]
        out = derive_features(values, definitions)
        self.assertEqual([row["lag"] for row in out], [None, 1, 2, 4, None])
        self.assertEqual([row["difference"] for row in out], [None, 1, 2, None, None])
        self.assertEqual([row["pct_change"] for row in out], [None, 1, 1, None, None])
        self.assertEqual([row["mean"] for row in out], [None, 1.5, 3, None, None])
        self.assertEqual([row["sum"] for row in out], [None, 3, 6, None, None])
        self.assertEqual([row["zscore"] for row in out], [None, 1, 1, None, None])
        self.assertEqual(values, [{"x": x} for x in [1.0, 2.0, 4.0, None, 8.0]])

    def test_transform_prefix_causality_chaining_and_zero_denominators(self):
        data = [{"x": x} for x in [1, 2, 4, 999, -999]]
        transforms = [
            {"source": "x", "name": "average", "operation": "mean", "window": 2},
            {"source": "average", "name": "lagged_average", "operation": "lag", "window": 1},
        ]
        out = derive_features(data, transforms)
        self.assertEqual(derive_features(data[:3], transforms), out[:3])
        self.assertEqual(out[2]["lagged_average"], 1.5)
        zeros = derive_features(
            [{"x": 0}, {"x": 0}],
            [
                {"source": "x", "name": "percent", "operation": "pct_change"},
                {"source": "x", "name": "z", "operation": "zscore", "window": 2},
            ],
        )
        self.assertIsNone(zeros[1]["percent"])
        self.assertEqual(zeros[1]["z"], 0)

    def test_transform_invalid_names_types_windows_and_operations_reject(self):
        valid = {"source": "x", "name": "new", "operation": "lag", "window": 1}
        for change in (
            {"window": 0},
            {"window": 1001},
            {"window": 1.5},
            {"window": True},
            {"window": "bad"},
            {"source": "absent"},
            {"name": "x"},
            {"operation": "future_mean"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                derive_features([{"x": 1}, {"x": 2}], [{**valid, **change}])
        with self.assertRaises(ValueError):
            derive_features([{"x": 1}], [None])


class ArbitraryResearchTests(unittest.TestCase):
    def test_icecream_merch_and_unusual_feature_combination_has_fifty_hand_calculated_fills(self):
        rows = [
            {
                "observed_at": (START + timedelta(days=i, hours=6)).isoformat(),
                "available_at": (START + timedelta(days=i, hours=9)).isoformat(),
                "ice_cream_sales": 200,
                "merch_sales": 70,
                "rubber_duck_sales": 20,
            }
            for i in range(50)
        ]
        body = rule_payload(
            rows, ["ice_cream_sales", "merch_sales", "rubber_duck_sales"], final_close=120
        )
        body["strategy"]["entry"] = {
            "all": [
                {"left": "event:ice_cream_sales", "op": ">", "right": 120},
                {"left": "event:merch_sales", "op": ">", "right": 65},
                {"left": "event:rubber_duck_sales", "op": ">", "right": 10},
            ]
        }
        body["execution"]["initial_cash"] = 1000
        run = run_experiment(body, persist=False)
        self.assertEqual(run["summary"]["trade_count"], 50)
        self.assertAlmostEqual(run["ledger"][-1]["cash"], 500)
        self.assertAlmostEqual(run["ledger"][-1]["units"], 5)
        self.assertAlmostEqual(run["summary"]["final_equity"], 1100)
        self.assertAlmostEqual(run["summary"]["total_return"], 0.1)
        self.assertEqual(
            run["strategy"]["fills"][0]["filled_at"], (START + timedelta(days=1)).isoformat()
        )
        self.assertEqual(
            run["strategy"]["fills"][-1]["filled_at"], (START + timedelta(days=50)).isoformat()
        )

    def test_annual_city_feature_rule_uses_chosen_year_expiry_instead_of_two_days(self):
        body = rule_payload(
            [
                {
                    "observed_at": START.isoformat(),
                    "available_at": START.isoformat(),
                    "city_index": 103,
                }
            ],
            ["city_index"],
            age=8760,
            market_count=520,
        )
        run = run_experiment(body, persist=False)
        self.assertEqual(run["summary"]["trade_count"], 365)
        self.assertAlmostEqual(run["ledger"][-1]["cash"], 6350)
        self.assertAlmostEqual(run["ledger"][-1]["units"], 36.5)
        self.assertEqual(run["configuration"]["strategy"]["event_max_age_hours"], 8760)

    def test_generic_rules_do_not_continue_buying_when_latest_value_is_explicitly_missing(self):
        body = rule_payload(observations([10, None]), ["sales"], age=48, market_count=4)
        run = run_experiment(body, persist=False)
        self.assertEqual(run["summary"]["trade_count"], 1)
        self.assertEqual(
            run["strategy"]["fills"][0]["filled_at"], (START + timedelta(days=1)).isoformat()
        )

    def test_nonmarket_training_target_and_full_feature_mapping_rerun_are_reproducible(self):
        rows = []
        for i in range(160):
            rows.append(
                {
                    "observed_at": (START + timedelta(days=i, hours=6)).isoformat(),
                    "available_at": (START + timedelta(days=i, hours=9)).isoformat(),
                    "traffic_count": 100 + 10 * math.sin(i / 4),
                    "merch_sales": [1, 3, 2, 4][i % 4],
                }
            )
        body = rule_payload(rows, ["traffic_count", "merch_sales"], market_count=160)
        body.update(
            mode="model",
            model_config={
                "feature_names": ["traffic_count", "merch_sales"],
                "target_field": "merch_sales",
                "target_type": "increase",
                "horizon": 1,
                "epochs": 30,
                "l2_candidates": [0.1],
                "seed": 42,
            },
        )
        first = run_experiment(body, persist=False)
        rerun = run_experiment(rerun_payload(first), persist=False)
        self.assertEqual(first["id"], rerun["id"])
        self.assertEqual(first["model"]["model"], rerun["model"]["model"])
        self.assertEqual(first["strategy"]["fills"], rerun["strategy"]["fills"])
        self.assertEqual(first["model"]["configuration"]["target_field"], "merch_sales")
        self.assertIn("merch_sales", first["model"]["target"])


if __name__ == "__main__":
    unittest.main()
