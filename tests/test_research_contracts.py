import copy
import math
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from hypothesis_lab.algorithms import SignalInterpreter, plan_algorithm
from hypothesis_lab.compute import _task
from hypothesis_lab.data import Bar
from hypothesis_lab.local_inference import run_endpoint_model
from hypothesis_lab.models import run_tabular_model


class NumericAndLanguageContracts(unittest.TestCase):
    def test_trailing_values_recover_after_large_value_leaves_window(self):
        read = SignalInterpreter([{"x": x} for x in [1e16, 1, 1, 1, 1]]).run
        self.assertEqual(read("sum(x,2)")[2:], [2, 2, 2])
        self.assertEqual(read("mean(x,2)")[2:], [1, 1, 1])
        huge = SignalInterpreter([{"x": 1e308}, {"x": 1e308}]).run("mean(x,2)")
        self.assertEqual(huge, [None, 1e308])
        self.assertEqual(read("clip(x,10,0)"), [None] * 5)

    def test_natural_cash_conjunction_and_threshold_precision(self):
        plan = plan_algorithm(
            "Buy $100 when horror share is above 0.35 and horror change 20 is greater than 0; sell when horror share is below 0.30.",
            ["horror_share", "horror_change_20"],
        )
        self.assertTrue(plan["executable"], plan)
        self.assertEqual(plan["draft"]["amount"], 100)
        precision = plan_algorithm("Buy when x > 1234567", ["x"])
        self.assertEqual(
            SignalInterpreter([{"x": 1234568}, {"x": 1234566}]).run(precision["draft"]["entry"]),
            [True, False],
        )

    def test_spoken_trailing_changes_and_missing_measurements(self):
        plan = plan_algorithm(
            "Buy $50 when rubber duck sales rises by more than 5% over seven bars; sell when price is below its twenty-bar average.",
            ["rubber_duck_sales"],
        )
        self.assertTrue(plan["executable"], plan)
        self.assertIn("pct_change", plan["draft"]["entry"])
        self.assertIn("mean", plan["draft"]["exit"])
        self.assertFalse(
            plan_algorithm("Buy when unicorn happiness is above 7", ["sales"])["executable"]
        )


class ComputeConditionSchema(unittest.TestCase):
    def test_external_target_can_differ_from_inputs_using_the_same_plain_field_grammar(self):
        task = {
            "feature_names": ["predictor"],
            "target_type": "condition",
            "target_condition": "outcome > mean(outcome,7)",
            "horizon": 3,
            "training_end": "2023-12-31T23:59:59Z",
        }
        self.assertEqual(_task(task, "train")["target_condition"], task["target_condition"])
        with self.assertRaisesRegex(ValueError, "grammar"):
            _task({**task, "target_condition": "outcome + 1"}, "train")


class CustomTargetContracts(unittest.TestCase):
    def data(self):
        start = datetime(2024, 1, 1, tzinfo=UTC)
        bars = [
            Bar(
                start + timedelta(days=i),
                100 + i / 10,
                102 + i / 10,
                99 + i / 10,
                101 + i / 10,
                100,
            )
            for i in range(180)
        ]
        rows = [
            {
                "knitting_searches": 100 + math.sin(i / 3) * 20,
                "resets": float(i % 7),
                "market.close": b.close,
            }
            for i, b in enumerate(bars)
        ]
        return bars, rows

    def test_user_condition_is_future_label_and_purged_from_training(self):
        bars, rows = self.data()
        config = {
            "feature_names": ["resets", "knitting_searches"],
            "target_type": "condition",
            "target_condition": 'col("knitting_searches") > mean(col("knitting_searches"),7)',
            "horizon": 3,
            "epochs": 20,
            "l2_candidates": [0.1],
            "data_delay_ms": 100,
        }
        result = run_tabular_model(bars, rows, config)
        future = SignalInterpreter(rows).run(config["target_condition"])
        for record in result["inference_decisions"]:
            self.assertEqual(record["actual"], float(future[record["index"] + 3]))
            self.assertIn(".100000", record["decision_at"])
        self.assertLess(
            result["splits"]["train"]["last_label_index"],
            result["splits"]["validation"]["first_index"],
        )
        self.assertIn("target_condition", result["model"])
        changed = copy.deepcopy(rows)
        for row in changed[150:]:
            row["knitting_searches"] += 1000
        second = run_tabular_model(bars, changed, config)
        self.assertEqual(result["model"], second["model"])
        self.assertEqual(result["search"], second["search"])

    def test_nonboolean_or_unavailable_target_is_rejected(self):
        bars, rows = self.data()
        with self.assertRaisesRegex(ValueError, "boolean"):
            run_tabular_model(
                bars,
                rows,
                {
                    "feature_names": ["resets"],
                    "target_type": "condition",
                    "target_condition": "resets",
                },
            )
        with self.assertRaisesRegex(ValueError, "not mapped"):
            run_tabular_model(
                bars,
                rows,
                {
                    "feature_names": ["resets"],
                    "target_type": "condition",
                    "target_condition": "unicorns > 1",
                },
            )


class ExternalConditionContracts(unittest.TestCase):
    data = CustomTargetContracts.data

    def test_batched_service_can_process_full_history_and_honors_custom_target(self):
        bars, rows = self.data()
        requests = []

        def service(connection, body, credential):
            requests.append(body)
            return {"predictions": [0.6] * len(body["features"])}

        config = {
            "feature_names": ["resets"],
            "target_type": "condition",
            "target_condition": "knitting_searches > mean(knitting_searches,7)",
            "horizon": 3,
            "evaluation_start_index": 0,
            "include_inference_latency": False,
        }
        with patch("hypothesis_lab.local_inference._request", service):
            result = run_endpoint_model(
                bars,
                rows,
                config,
                {"kind": "tabular", "endpoint": "http://127.0.0.1:9999/predict", "max_calls": 1},
            )
        self.assertEqual(len(requests), 1)
        self.assertEqual(len(requests[0]["features"]), 179)
        self.assertIn("target_condition", result["configuration"])
        self.assertIn("log_loss", result["test"])
        self.assertEqual(
            result["inference_decisions"][15]["actual"],
            float(SignalInterpreter(rows).run(config["target_condition"])[18]),
        )
        with patch("hypothesis_lab.local_inference._request") as blocked:
            with self.assertRaisesRegex(ValueError, "overlaps"):
                run_endpoint_model(
                    bars,
                    rows,
                    {**config, "trained_through": bars[10].timestamp.isoformat()},
                    {"kind": "tabular", "endpoint": "http://127.0.0.1:9999/predict"},
                )
            blocked.assert_not_called()
