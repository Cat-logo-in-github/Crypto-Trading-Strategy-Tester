"""Independent expectations for arbitrary inputs, targets and safe model replay."""

import base64
import builtins
import copy
import hashlib
import json
import math
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hypothesis_lab.data import Bar
from hypothesis_lab.models import (
    MODEL_SCHEMA,
    _decision_config,
    fit_tabular,
    infer_uploaded,
    inspect_uploaded,
    predict_tabular,
    prediction_decision,
    run_tabular_model,
)

START = datetime(2021, 1, 1, tzinfo=UTC)


def data(count=180):
    bars, rows = [], []
    for index in range(count):
        signal = 1.0 if math.sin((index + 1) / 4) > math.sin(index / 4) else -1.0
        opened = 100 + index * 0.03
        closed = opened * (0.99 if index % 2 else 1.01)
        bars.append(
            Bar(
                START + timedelta(days=index),
                opened,
                max(opened, closed) + 1,
                min(opened, closed) - 1,
                closed,
                100,
            )
        )
        rows.append(
            {
                "traffic_count": 100 + 10 * math.sin(index / 4),
                "predictor": signal,
                "urban_index": index / 100,
            }
        )
    return bars, rows


def logistic_model(name="model_input"):
    # The normalized score x*ln(3) gives exactly 0.75 at x=1 and 0.25 at x=-1.
    return {
        "schema": MODEL_SCHEMA,
        "family": "logistic",
        "feature_names": [name],
        "means": [0.0],
        "scales": [1.0],
        "coefficients": [math.log(3)],
        "intercept": 0.0,
    }


def training_config(**updates):
    return {
        "feature_names": ["predictor"],
        "target_field": "traffic_count",
        "target_type": "increase",
        "horizon": 1,
        "epochs": 80,
        "l2_candidates": [0.001, 0.1],
        **updates,
    }


class TabularModelTests(unittest.TestCase):
    def test_logistic_numeric_json_has_hand_calculated_probabilities_and_mapping(self):
        model = json.loads(json.dumps(logistic_model()))
        self.assertAlmostEqual(predict_tabular(model, {"model_input": 1}), 0.75)
        self.assertAlmostEqual(predict_tabular(model, [-1]), 0.25)
        predictions, descriptor = infer_uploaded(
            model,
            [{"local_measure": 1}, {"local_measure": -1}],
            {"feature_mapping": {"model_input": "local_measure"}},
        )
        self.assertEqual(descriptor["feature_names"], ["model_input"])
        self.assertAlmostEqual(predictions[0], 0.75)
        self.assertAlmostEqual(predictions[1], 0.25)

    def test_threshold_comparison_cash_budget_and_false_hold_are_explicit(self):
        policy = _decision_config(
            {
                "decision": {
                    "comparison": ">",
                    "threshold": 0.5,
                    "when_true": {"buy_cash": 125},
                    "when_false": "hold",
                }
            },
            "probability",
        )
        decision, matched = prediction_decision(0.75, policy)
        self.assertTrue(matched)
        self.assertEqual(decision.buy_cash, 125)
        self.assertEqual(prediction_decision(0.5, policy), (None, False))
        policy["comparison"] = ">="
        self.assertTrue(prediction_decision(0.5, policy)[1])
        for value in (-0.1, 1.1, float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                prediction_decision(value, policy)

    def test_arbitrary_external_target_is_not_replaced_by_market_return(self):
        bars, rows = data()
        result = run_tabular_model(bars, rows, training_config())
        self.assertIn("traffic_count", result["target"])
        for row in result["predictions"]:
            index = row["index"]
            expected = float(rows[index + 1]["traffic_count"] > rows[index]["traffic_count"])
            self.assertEqual(row["actual"], expected)
        self.assertEqual(result["model"]["output_kind"], "probability")
        self.assertGreater(result["test"]["accuracy"], 0.9)
        self.assertFalse(result["search"]["test_used_for_selection"])

    def test_chronological_labels_are_purged_on_raw_bar_boundaries(self):
        bars, rows = data()
        result = run_tabular_model(bars, rows, training_config(horizon=3))
        splits = result["splits"]
        self.assertLess(splits["train"]["last_label_index"], splits["validation"]["first_index"])
        self.assertLess(splits["validation"]["last_label_index"], splits["test"]["first_index"])
        self.assertEqual(splits["purge_bars"], 3)
        self.assertGreaterEqual(splits["purged_rows"], 6)

    def test_held_out_values_cannot_change_fitted_scaling_model_or_selected_penalty(self):
        bars, rows = data()
        original = run_tabular_model(bars, rows, training_config())
        future = copy.deepcopy(rows)
        boundary = int(len(rows) * 0.8)
        for row in future[boundary:]:
            row["predictor"] *= -50
            row["traffic_count"] += 50000
        perturbed = run_tabular_model(bars, future, training_config())
        self.assertEqual(original["model"], perturbed["model"])
        self.assertEqual(original["search"], perturbed["search"])
        self.assertEqual(original["validation"], perturbed["validation"])

    def test_missing_inputs_are_dropped_and_missing_inference_does_not_fabricate_orders(self):
        bars, rows = data()
        rows[5]["predictor"] = None
        rows[150]["predictor"] = None
        result = run_tabular_model(bars, rows, training_config())
        self.assertTrue(any("missing" in warning.lower() for warning in result["warnings"]))
        self.assertNotIn(150, [record["index"] for record in result["inference_decisions"]])
        self.assertNotIn(
            bars[150].timestamp.isoformat(),
            [fill["decision_bar_open"] for fill in result["backtest"]["fills"]],
        )

    def test_uploaded_model_mapping_next_open_fees_and_discrepancy_records(self):
        bars, rows = data(8)
        rows[0]["predictor"] = 1
        rows[1]["predictor"] = -1
        config = training_config(
            evaluation_start_index=0,
            feature_mapping={"model_input": "predictor"},
            initial_cash=1000,
            fee_bps=100,
            slippage_bps=100,
            decision={
                "threshold": 0.5,
                "comparison": ">",
                "when_true": {"buy_cash": 100},
                "when_false": "exit",
            },
        )
        result = run_tabular_model(bars, rows, config, logistic_model())
        self.assertEqual(result["splits"]["train"]["rows"], 0)
        self.assertEqual(result["search"]["trial_count"], 0)
        first = result["inference_decisions"][0]
        self.assertTrue(first["condition_matched"])
        self.assertEqual(first["execution_status"], "filled")
        fill = first["fills"][0]
        self.assertEqual(fill["filled_at"], bars[1].timestamp.isoformat())
        self.assertAlmostEqual(fill["price"], bars[1].open * 1.01)
        self.assertAlmostEqual(fill["quantity"], 100 / (bars[1].open * 1.01 * 1.01))
        self.assertEqual(first["features"], {"predictor": 1.0})
        self.assertTrue(any("unknown" in warning.lower() for warning in result["warnings"]))
        self.assertIn("discrepancy_summary", result)
        json.dumps(result, allow_nan=False)

    def test_declared_pretraining_overlap_is_rejected(self):
        bars, rows = data(20)
        model = logistic_model("predictor")
        model["trained_through"] = (bars[10].timestamp + timedelta(days=2)).isoformat()
        with self.assertRaisesRegex(ValueError, "overlaps"):
            run_tabular_model(bars, rows, training_config(evaluation_start_index=10), model)
        model["trained_through"] = START.isoformat()
        result = run_tabular_model(bars, rows, training_config(evaluation_start_index=10), model)
        self.assertTrue(any("user declarations" in warning for warning in result["warnings"]))

    def test_ridge_learns_named_non_market_future_level_and_safe_roundtrip(self):
        rows = [[float(index), float(index % 2)] for index in range(40)]
        targets = [2 * row[0] + 3 for row in rows]
        model = fit_tabular(
            rows, targets, ["arbitrary_count", "category_hash"], family="ridge", l2=0.001
        )
        self.assertAlmostEqual(
            predict_tabular(json.loads(json.dumps(model)), [12, 0]), 27, delta=0.01
        )
        bars, features = data()
        result = run_tabular_model(
            bars, features, training_config(target_type="level", model_family="ridge")
        )
        self.assertEqual(result["model"]["target_field"], "traffic_count")
        self.assertEqual(result["model"]["output_kind"], "prediction")

    def test_malformed_artifacts_pickle_unknown_fields_and_nonfinite_values_are_rejected(self):
        for model in (
            {"format": "pickle"},
            {**logistic_model(), "scales": [0]},
            {**logistic_model(), "coefficients": [float("nan")]},
            {**logistic_model(), "feature_names": ["", "same"]},
        ):
            with self.subTest(model=model.get("format", "json")), self.assertRaises(ValueError):
                inspect_uploaded(model)
        bars, rows = data()
        for config in (
            training_config(feature_names=["absent"]),
            training_config(target_field="absent"),
            training_config(horizon=0),
            training_config(train_fraction=0.9, validation_fraction=0.2),
            training_config(l2_candidates=[0]),
            training_config(epochs=2001),
        ):
            with self.subTest(config=config), self.assertRaises(ValueError):
                run_tabular_model(bars, rows, config)
        rows[5]["predictor"] = float("inf")
        with self.assertRaises(ValueError):
            run_tabular_model(bars, rows, training_config())
        for mapping in ({"model_input": []}, {"model_input": ""}, {"absent_input": "predictor"}):
            with self.subTest(mapping=mapping), self.assertRaises(ValueError):
                infer_uploaded(logistic_model(), [{"predictor": 1}], {"feature_mapping": mapping})

    def test_local_onnx_and_uploaded_bytes_report_the_actual_same_graph_sha256(self):
        graph = b"synthetic graph bytes for hashing contract"
        info = SimpleNamespace(name="input", shape=[None, 1], type="tensor(float)")

        class Session:
            def __init__(self, *args, **kwargs):
                pass

            def get_inputs(self):
                return [info]

            def get_outputs(self):
                return [SimpleNamespace(name="probability", shape=[None, 1], type="tensor(float)")]

        runtime = SimpleNamespace(SessionOptions=SimpleNamespace, InferenceSession=Session)
        temporary_root = Path(__file__).resolve().parents[1] / "work" / "test-models"
        temporary_root.mkdir(parents=True, exist_ok=True)
        with (
            tempfile.TemporaryDirectory(dir=temporary_root) as directory,
            patch.dict("sys.modules", {"onnxruntime": runtime}),
        ):
            file = Path(directory) / "model.onnx"
            file.write_bytes(graph)
            local = inspect_uploaded(
                {"format": "onnx", "model_path": str(file), "allow_local_file": True}
            )
            uploaded = inspect_uploaded(
                {"format": "onnx", "data_base64": base64.b64encode(graph).decode()}
            )
        self.assertEqual(local["sha256"], hashlib.sha256(graph).hexdigest())
        self.assertEqual(local["sha256"], uploaded["sha256"])

    def test_training_is_deterministic_with_bounded_search(self):
        bars, rows = data()
        first = run_tabular_model(bars, rows, training_config())
        self.assertEqual(first, run_tabular_model(bars, rows, training_config()))
        self.assertLessEqual(first["search"]["trial_count"], 8)

    def test_onnx_missing_runtime_returns_actionable_optional_install_error(self):
        original_import = builtins.__import__

        def without_onnx(name, *args, **kwargs):
            if name == "onnxruntime":
                raise ImportError("optional runtime absent")
            return original_import(name, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=without_onnx),
            self.assertRaisesRegex(ValueError, r"hypothesis-lab\[onnx\]"),
        ):
            inspect_uploaded({"format": "onnx", "data_base64": ""})

    def test_uploaded_numeric_scores_do_not_acquire_probability_diagnostics(self):
        bars, rows = data(20)
        model = {**logistic_model("predictor"), "family": "linear", "coefficients": [3]}
        result = run_tabular_model(bars, rows, training_config(evaluation_start_index=10), model)
        self.assertNotIn("log_loss", result["test"])
        self.assertNotIn("accuracy", result["test"])
        self.assertNotIn("directional_accuracy", result["test"])
        self.assertTrue(all(record["forecast_correct"] is None for record in result["predictions"]))
        self.assertTrue(
            any("not calibrated probabilities" in warning for warning in result["warnings"])
        )


if __name__ == "__main__":
    unittest.main()
