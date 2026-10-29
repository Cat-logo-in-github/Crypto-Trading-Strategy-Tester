"""Chronological ML contract checks using generated, offline data."""

import json
import math
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from hypothesis_lab.data import Bar
from hypothesis_lab.ml import fit_ridge, predict, run_ml, trailing_features


def synthetic_bars(count=180):
    bars = []
    previous = 100.0
    for i in range(count):
        close = 100 + i * 0.1 + 4 * math.sin(i / 6) + math.sin(i / 2)
        bars.append(
            Bar(
                timestamp=datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=i),
                open=previous,
                high=max(previous, close) + 1,
                low=min(previous, close) - 1,
                close=close,
                volume=1000 + 100 * math.cos(i / 3),
            )
        )
        previous = close
    return bars


class MLTests(unittest.TestCase):
    def test_known_linear_relationship_and_json_inference(self):
        features = [[float(i)] for i in range(10)]
        targets = [2 * row[0] + 3 for row in features]
        model = fit_ridge(features, targets, ["return_1"], alpha=1e-8)
        restored = json.loads(json.dumps(model, allow_nan=False))
        self.assertAlmostEqual(predict(restored, {"return_1": 4.5}), 12, places=6)
        self.assertAlmostEqual(predict(restored, [12.0]), 27, places=6)
        self.assertEqual(model["means"], [4.5])

    def test_trailing_features_do_not_read_future(self):
        bars = synthetic_bars()
        features = trailing_features(bars, 30)
        changed = bars[:31] + [
            replace(
                bar,
                open=bar.open * 2,
                high=bar.high * 2,
                low=bar.low * 2,
                close=bar.close * 2,
            )
            for bar in bars[31:]
        ]
        self.assertEqual(features, trailing_features(changed, 30))

    def test_horizon_labels_are_purged_between_periods(self):
        result = run_ml(synthetic_bars(), {"horizon": 5})
        split = result["splits"]
        self.assertLess(split["train"]["last_label_index"], split["validation"]["first_index"])
        self.assertLess(split["validation"]["last_label_index"], split["test"]["first_index"])
        self.assertEqual(split["purged_rows"], 10)
        self.assertFalse(result["search"]["test_used_for_selection"])

    def test_future_test_prices_cannot_change_fitted_model_or_selection(self):
        bars = synthetic_bars()
        original = run_ml(bars, {"horizon": 3})
        boundary = original["splits"]["test"]["first_index"]
        changed = bars[:boundary] + [
            replace(
                bar,
                open=bar.open * 2,
                high=bar.high * 2,
                low=bar.low * 2,
                close=bar.close * 2,
                volume=bar.volume * 3,
            )
            for bar in bars[boundary:]
        ]
        altered = run_ml(changed, {"horizon": 3})
        self.assertEqual(original["model"], altered["model"])
        self.assertEqual(original["search"], altered["search"])
        self.assertEqual(original["validation"], altered["validation"])

    def test_run_is_repeatable_and_artifact_can_be_used_for_inference(self):
        bars = synthetic_bars()
        first = run_ml(bars)
        second = run_ml(bars)
        self.assertEqual(first, second)
        restored = json.loads(json.dumps(first, allow_nan=False))
        row = first["predictions"][0]
        self.assertEqual(
            row["prediction"], predict(restored["model"], trailing_features(bars, row["index"]))
        )
        self.assertEqual(
            first["backtest"]["equity"][0]["timestamp"],
            first["benchmark"]["equity"][0]["timestamp"],
        )

    def test_invalid_splits_sizes_inputs_and_artifacts_are_rejected(self):
        bars = synthetic_bars()
        for configuration in (
            {"horizon": 0},
            {"horizon": 1.5},
            {"train_fraction": 0.9, "validation_fraction": 0.2},
            {"feature_names": ["future_return"]},
            {"ridge_alphas": [0]},
            {"ridge_alphas": [float("nan")]},
            {"model_family": "invented"},
        ):
            with self.subTest(configuration=configuration), self.assertRaises(ValueError):
                run_ml(bars, configuration)
        with self.assertRaises(ValueError):
            run_ml(bars[:25])
        with self.assertRaises(ValueError):
            run_ml([bars[1], bars[0], *bars[2:]])
        with self.assertRaises(ValueError):
            run_ml([replace(bars[0], close=float("nan")), *bars[1:]])
        with self.assertRaises(ValueError):
            predict({"schema": "pickle"}, [1.0])
        model = fit_ridge([[1.0], [2.0]], [1.0, 2.0], ["return_1"])
        model["scales"] = [0]
        with self.assertRaises(ValueError):
            predict(model, [1.0])


if __name__ == "__main__":
    unittest.main()
