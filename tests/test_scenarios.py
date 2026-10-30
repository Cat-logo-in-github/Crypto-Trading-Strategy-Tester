"""Cross-format scenario trials through the actual research and accounting pipeline."""

import copy
import json
import unittest
from datetime import timedelta

from hypothesis_lab.data import load_bars
from hypothesis_lab.features import align_features, prepare_dataset, read_records
from hypothesis_lab.research import rerun_payload, run_experiment
from hypothesis_lab.scenarios import (
    BOX,
    DAYS,
    IDS,
    catalogue,
    prefix_causality,
    run_scenarios,
    scenario_payload,
)


class ScenarioCatalogueTests(unittest.TestCase):
    def test_five_distinct_measurable_structures_and_mutation_isolation(self):
        items = catalogue()
        self.assertEqual(len(items), 5)
        self.assertEqual(
            {item["format"] for item in items}, {"csv", "ndjson", "geojson", "json", "tsv"}
        )
        self.assertEqual(len({item["seed"] for item in items}), 5)
        self.assertTrue(all("synthetic" in item["data_status"].lower() for item in items))
        items[0]["limits"].append("mutated")
        self.assertNotIn("mutated", catalogue()[0]["limits"])
        with self.assertRaises(ValueError):
            scenario_payload("not-a-scenario")
        with self.assertRaises(ValueError):
            scenario_payload(IDS[0], days=True)
        with self.assertRaisesRegex(ValueError, "provenance"):
            scenario_payload(IDS[0], market_csv="private market")

    def test_fixture_market_is_independent_of_scenario_and_payload_is_deterministic(self):
        first = scenario_payload(IDS[0])
        self.assertEqual(first, scenario_payload(IDS[0]))
        self.assertEqual(first["market_csv"], scenario_payload(IDS[4])["market_csv"])
        self.assertFalse(first["persist_local"])
        self.assertIn("synthetic", first["provenance_note"])
        json.dumps(first, allow_nan=False)

    def test_monthly_panel_selects_one_entity_and_does_not_treat_dates_as_features(self):
        body = scenario_payload(IDS[0])
        observations, info = prepare_dataset(
            body["feature_data"], body["feature_format"], body["feature_mapping"]
        )
        self.assertEqual(info["generated_fields"], ["horror_loans", "all_loans"])
        self.assertEqual(info["mapping"]["timestamp_parts"], {"year": "Year", "month": "Month"})
        self.assertEqual(info["quality"]["selected_rows"], 14)
        self.assertEqual(len(observations), 14)
        self.assertEqual(observations[0].observed_at.month, 2)
        self.assertGreater(observations[0].available_at, observations[0].observed_at)

    def test_nested_event_notes_are_explicit_numeric_measurements(self):
        body = scenario_payload(IDS[1])
        observations, info = prepare_dataset(
            body["feature_data"], "ndjson", body["feature_mapping"]
        )
        self.assertIn("repair.completed", info["generated_fields"])
        self.assertIn("burnt_mentions", info["generated_fields"])
        self.assertEqual(observations[0].values["burnt_mentions"], 1)
        self.assertEqual(observations[2].values["burnt_mentions"], 0)
        self.assertLess(observations[0].observed_at, observations[0].available_at)

    def test_point_geometry_region_filter_and_actual_event_count_agree(self):
        body = scenario_payload(IDS[2])
        rows = read_records(body["feature_data"], "geojson")
        south, west, north, east = BOX
        for row in rows:
            inside = south <= row["_latitude"] <= north and west <= row["_longitude"] <= east
            self.assertEqual(row["inside_plaza"], inside)
        observations, info = prepare_dataset(
            body["feature_data"], "geojson", body["feature_mapping"]
        )
        self.assertEqual(info["generated_fields"], ["event_count"])
        self.assertEqual(len(observations), DAYS)
        self.assertEqual(
            sum(item.values["event_count"] for item in observations),
            sum(row["inside_plaza"] for row in rows),
        )
        self.assertTrue(all(item.available_at >= item.observed_at for item in observations))
        self.assertEqual(info["mapping"]["filter"]["equals"], True)


class ScenarioPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = run_scenarios(include_controls=True, include_records=True)
        cls.by_id = {item["scenario"]["id"]: item for item in cls.report["scenarios"]}

    def test_all_five_run_complete_ingestion_inference_accounting_and_replay(self):
        self.assertEqual(set(self.by_id), set(IDS))
        for item in self.by_id.values():
            with self.subTest(identity=item["scenario"]["id"]):
                run, score = item["run"], item["score"]
                self.assertTrue(item["prefix_causality"]["passed"])
                self.assertTrue(item["replay_identical"])
                self.assertEqual(run["id"], run_experiment(rerun_payload(run), persist=False)["id"])
                self.assertEqual(score["trade_count"], len(run["strategy"]["fills"]))
                self.assertEqual(run["summary"]["final_equity"], run["ledger"][-1]["equity"])
                self.assertEqual(run["benchmark"]["config"], run["strategy"]["config"])
                self.assertTrue(
                    all(row["cash"] >= 0 and row["units"] >= 0 for row in run["ledger"])
                )
                self.assertGreater(len(run["diagnostics"]["inference_decisions"]), 50)
                json.dumps(item, allow_nan=False)

    def test_external_targets_have_purged_heldout_model_tests(self):
        for identity in (IDS[1], IDS[4]):
            with self.subTest(identity=identity):
                model = self.by_id[identity]["run"]["model"]
                splits = model["splits"]
                self.assertLess(
                    splits["train"]["last_label_index"], splits["validation"]["first_index"]
                )
                self.assertLess(
                    splits["validation"]["last_label_index"], splits["test"]["first_index"]
                )
                self.assertFalse(model["search"]["test_used_for_selection"])
                self.assertNotEqual(model["configuration"]["target_field"], "market.close")
                self.assertGreaterEqual(splits["test"]["rows"], 6)
        config = self.by_id[IDS[4]]["run"]["model"]["configuration"]
        self.assertEqual(config["target_type"], "condition")
        self.assertIn("mean", config["target_condition"])

    def test_uploaded_artifact_uses_mapping_without_claiming_training(self):
        item = self.by_id[IDS[3]]
        model = item["run"]["model"]
        self.assertEqual(model["search"]["objective"], "none: uploaded model inference only")
        self.assertEqual(model["splits"]["train"]["rows"], 0)
        self.assertIn("hand-authored", " ".join(item["scenario"]["limits"]))
        self.assertEqual(model["configuration"]["feature_mapping"]["authentic"], "authentic_count")
        predictions = model["inference_decisions"]
        self.assertTrue(all(0 <= row["prediction"] <= 1 for row in predictions))

    def test_fixed_sensitivity_and_missing_publication_controls_are_not_selected_by_return(self):
        returns = []
        for item in self.by_id.values():
            controls = {control["kind"]: control for control in item["controls"]}
            self.assertEqual(
                set(controls),
                {
                    "higher_costs",
                    "fixed_threshold_perturbation",
                    "unavailable_publication_negative_control",
                },
            )
            self.assertTrue(controls["unavailable_publication_negative_control"]["passed"])
            returns.append(item["score"]["total_return"])
        # Fixed seeds deliberately preserve good, bad and abstaining outcomes.
        self.assertTrue(any(value > 0 for value in returns))
        self.assertTrue(any(value < 0 for value in returns))
        self.assertIn("not evidence", self.by_id[IDS[0]]["score"]["label"])
        self.assertTrue(self.report["audit_recommendations"])

    def test_future_publications_and_bars_do_not_change_earlier_measurements(self):
        for identity in IDS:
            with self.subTest(identity=identity):
                self.assertTrue(prefix_causality(scenario_payload(identity))["passed"])
        body = scenario_payload(IDS[1])
        bars = load_bars(body["market_csv"], content=True)
        observations, info = prepare_dataset(
            body["feature_data"], "ndjson", body["feature_mapping"]
        )
        first = align_features(bars[:10], observations, info)
        future = copy.deepcopy(observations[-1])
        from hypothesis_lab.features import Observation

        moved = Observation(
            bars[-1].timestamp + timedelta(days=100),
            future.available_at + timedelta(days=100),
            {name: 1e12 for name in future.values},
        )
        self.assertEqual(first, align_features(bars[:10], [*observations, moved], info))


if __name__ == "__main__":
    unittest.main()
