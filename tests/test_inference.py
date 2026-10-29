"""User-end model endpoints: privacy, bounded calls and reported signals."""

import io
import json
import math
import unittest
import urllib.error
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from hypothesis_lab.data import Bar
from hypothesis_lab.local_inference import (
    _NoRedirect,
    _request,
    call_llm,
    endpoint_url,
    extract_signal,
    llm_plan,
    public_connection,
    run_endpoint_model,
)


def data(count=20):
    start = datetime(2024, 1, 1, tzinfo=UTC)
    bars = [
        Bar(start + timedelta(days=i), 100, 101, 98, 99 if i % 2 else 100, 20) for i in range(count)
    ]
    rows = [{"traffic": i * 2.0, "not_selected_future_outcome": 100000 + i} for i in range(count)]
    return bars, rows


def connection(**updates):
    return {
        "endpoint": "http://127.0.0.1:1234/v1",
        "model": "user-local-model",
        "kind": "llm",
        "max_calls": 4,
        **updates,
    }


class EndpointInferenceTests(unittest.TestCase):
    def test_endpoint_requires_explicit_remote_opt_in_and_credentials_never_live_in_urls(self):
        self.assertEqual(endpoint_url(connection()), "http://127.0.0.1:1234/v1")
        self.assertEqual(
            endpoint_url(connection(endpoint="http://[::1]:1234/v1")), "http://[::1]:1234/v1"
        )
        self.assertEqual(
            endpoint_url(connection(endpoint="https://model.example/v1", allow_remote=True)),
            "https://model.example/v1",
        )
        for url in (
            "http://model.example/v1",
            "https://model.example/v1",
            "file:///model.onnx",
            "http://name:secret@localhost/v1",
            "http://localhost/v1?key=secret",
            "http://localhost/v1#secret",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                endpoint_url(connection(endpoint=url))

    def test_redirects_are_forbidden_before_an_authorization_header_can_be_forwarded(self):
        with self.assertRaisesRegex(ValueError, "not forwarded"):
            _NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://other.example")

    def test_request_only_sends_credential_to_selected_endpoint_and_sanitizes_errors(self):
        class Response(io.BytesIO):
            pass

        captured = []

        class Opener:
            def open(self, request, timeout):
                captured.append(request)
                return Response(b'{"value":0.75}')

        with patch(
            "hypothesis_lab.local_inference.urllib.request.build_opener", return_value=Opener()
        ):
            self.assertEqual(
                _request(connection(), {"value": 1}, "private-session-value"), {"value": 0.75}
            )
        self.assertEqual(captured[0].full_url, "http://127.0.0.1:1234/v1/chat/completions")
        self.assertEqual(captured[0].get_header("Authorization"), "Bearer private-session-value")
        self.assertNotIn("private-session-value", captured[0].data.decode())
        for error in (
            urllib.error.URLError("private-session-value"),
            urllib.error.HTTPError(
                "https://private-session-value", 401, "private-session-value", {}, None
            ),
        ):
            with patch("hypothesis_lab.local_inference.urllib.request.build_opener") as build:
                build.return_value.open.side_effect = error
                with self.assertRaises(ValueError) as raised:
                    _request(connection(), {}, "private-session-value")
                self.assertNotIn("private-session-value", str(raised.exception))

    def test_request_rejects_invalid_json_large_responses_and_nonobject_shapes(self):
        for content in (b"not-json", b"[]", b"a" * 1_000_001):
            with patch("hypothesis_lab.local_inference.urllib.request.build_opener") as build:
                build.return_value.open.return_value = io.BytesIO(content)
                with self.subTest(size=len(content)), self.assertRaises(ValueError):
                    _request(connection(), {})

    def test_chat_usage_is_reported_exactly_and_never_silently_estimated(self):
        response = {
            "choices": [{"message": {"content": '{"probability":0.75}'}}],
            "usage": {"completion_tokens": 17, "prompt_tokens": 25, "total_tokens": 42},
            "model": "reported-local-model",
        }
        with patch("hypothesis_lab.local_inference._request", return_value=response) as request:
            result = call_llm(connection(max_tokens=32), "features only", "session-key")
        self.assertEqual(
            (result["completion_tokens"], result["prompt_tokens"], result["total_tokens"]),
            (17, 25, 42),
        )
        self.assertEqual(result["reported_model"], "reported-local-model")
        self.assertEqual(request.call_args.args[1]["max_tokens"], 32)
        self.assertFalse(request.call_args.args[1]["stream"])
        response.pop("usage")
        with patch("hypothesis_lab.local_inference._request", return_value=response):
            result = call_llm(connection(), "x")
        self.assertIsNone(result["completion_tokens"])
        with self.assertRaisesRegex(ValueError, "never estimated"):
            extract_signal(result, {"signal": "completion_tokens"})

    def test_numeric_json_phrase_character_and_token_signal_extraction(self):
        response = {
            "text": '{"forecast":{"probability":0.75}}',
            "completion_tokens": 8,
            "prompt_tokens": 11,
            "total_tokens": 19,
        }
        self.assertEqual(
            extract_signal(
                response, {"signal": "json_field", "output_field": "forecast.probability"}
            ),
            0.75,
        )
        self.assertEqual(
            extract_signal(response, {"signal": "text_contains", "phrase": "FORECAST"}), 1.0
        )
        self.assertEqual(
            extract_signal(response, {"signal": "text_contains", "phrase": "missing"}), 0.0
        )
        self.assertEqual(extract_signal(response, {"signal": "text_length"}), len(response["text"]))
        self.assertEqual(extract_signal(response, {"signal": "completion_tokens"}), 8)
        for value in (float("nan"), float("inf"), "unknown"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                extract_signal({"completion_tokens": value}, {"signal": "completion_tokens"})
        with self.assertRaises(ValueError):
            extract_signal(response, {"signal": "json_field", "output_field": "missing"})

    def test_call_budget_and_prompt_placeholder_are_checked_before_requests(self):
        bars, rows = data()
        config = {"feature_names": ["traffic"], "evaluation_start_index": 0}
        for selected in (
            connection(max_calls=1),
            connection(max_calls=0),
            connection(max_calls=65),
            connection(max_calls=64, prompt="no placeholder"),
        ):
            with (
                patch("hypothesis_lab.local_inference.call_llm") as mocked,
                self.subTest(selected=selected),
                self.assertRaises(ValueError),
            ):
                run_endpoint_model(bars, rows, config, selected)
            mocked.assert_not_called()

    def test_historical_llm_replay_only_supplies_selected_current_features(self):
        bars, rows = data()
        prompts = []

        def local_model(config, prompt, credential):
            prompts.append(prompt)
            return {
                "text": '{"probability":0.75}',
                "completion_tokens": 8,
                "prompt_tokens": 12,
                "total_tokens": 20,
                "latency_seconds": 0.01,
            }

        config = {
            "feature_names": ["traffic"],
            "evaluation_start_index": 15,
            "initial_cash": 1000,
            "fee_bps": 100,
            "slippage_bps": 100,
            "decision": {
                "comparison": ">",
                "threshold": 0.5,
                "when_true": {"buy_cash": 100},
                "when_false": "hold",
            },
        }
        with patch("hypothesis_lab.local_inference.call_llm", side_effect=local_model):
            result = run_endpoint_model(bars, rows, config, connection(), "session-key")
        self.assertEqual(len(prompts), 4)
        for position, prompt in enumerate(prompts):
            self.assertIn(
                json.dumps({"traffic": rows[15 + position]["traffic"]}, sort_keys=True), prompt
            )
            self.assertNotIn("not_selected_future_outcome", prompt)
            self.assertNotIn("session-key", prompt)
        record = result["inference_decisions"][0]
        self.assertEqual(record["usage"]["completion_tokens"], 8)
        self.assertAlmostEqual(record["prediction"], 0.75)
        # The output is not ready at day16's open: 10ms of inference must
        # advance the fill to the next supplied open, rather than relabel time.
        self.assertEqual(record["fills"][0]["filled_at"], bars[17].timestamp.isoformat())
        self.assertAlmostEqual(record["fills"][0]["quantity"], 100 / (100 * 1.01 * 1.01))
        self.assertNotIn("session-key", json.dumps(result))
        self.assertTrue(any("future knowledge" in warning for warning in result["warnings"]))
        with patch("hypothesis_lab.local_inference.call_llm", side_effect=local_model):
            disabled = run_endpoint_model(
                bars, rows, {**config, "include_inference_latency": False}, connection()
            )
        self.assertEqual(
            disabled["inference_decisions"][0]["fills"][0]["filled_at"],
            bars[16].timestamp.isoformat(),
        )

    def test_tabular_endpoint_uses_ordered_features_and_one_output_per_row(self):
        bars, rows = data()
        config = {"feature_names": ["traffic"], "evaluation_start_index": 16}
        selected = connection(
            kind="tabular", output_field="result.predictions", output_kind="probability"
        )
        with patch(
            "hypothesis_lab.local_inference._request",
            return_value={"result": {"predictions": [0.25, 0.75, 0.5]}},
        ) as mocked:
            result = run_endpoint_model(bars, rows, config, selected)
        self.assertEqual(mocked.call_args.args[1]["features"], [[32.0], [34.0], [36.0]])
        self.assertEqual(
            [record["condition_matched"] for record in result["predictions"]], [False, True, False]
        )
        with (
            patch(
                "hypothesis_lab.local_inference._request",
                return_value={"result": {"predictions": [0.75]}},
            ),
            self.assertRaises(ValueError),
        ):
            run_endpoint_model(bars, rows, config, selected)

    def test_nonprobability_token_count_can_drive_an_explicit_rule(self):
        bars, rows = data()
        config = {
            "feature_names": ["traffic"],
            "evaluation_start_index": 18,
            "decision": {
                "comparison": ">=",
                "threshold": 9,
                "when_true": {"target_weight": 1},
                "when_false": "exit",
            },
        }
        with patch(
            "hypothesis_lab.local_inference.call_llm",
            return_value={
                "text": "short",
                "completion_tokens": 9,
                "prompt_tokens": 3,
                "total_tokens": 12,
            },
        ):
            result = run_endpoint_model(bars, rows, config, connection(signal="completion_tokens"))
        self.assertEqual(result["predictions"][0]["prediction"], 9)
        self.assertIsNone(result["predictions"][0]["probability"])
        self.assertTrue(result["predictions"][0]["condition_matched"])

    def test_plan_returns_candidates_without_executing_dataset_urls_or_code(self):
        content = {
            "search_terms": "urban mobility",
            "required_measurements": ["traffic counts"],
            "candidate_signal": "next-day increase",
            "clarifications": ["Which city?"],
        }
        with patch(
            "hypothesis_lab.local_inference.call_llm",
            return_value={
                "text": json.dumps(content),
                "completion_tokens": 10,
                "prompt_tokens": 20,
                "total_tokens": 30,
            },
        ):
            plan = llm_plan("test traffic", connection())
        self.assertEqual(plan["search_terms"], "urban mobility")
        self.assertIn("not executed", plan["warning"])
        self.assertEqual(plan["usage"]["total_tokens"], 30)
        with (
            patch("hypothesis_lab.local_inference.call_llm", return_value={"text": "not-json"}),
            self.assertRaises(ValueError),
        ):
            llm_plan("test", connection())

    def test_invalid_chat_shapes_and_output_budgets_are_rejected(self):
        for content in (
            {},
            {"choices": []},
            {"choices": [{"message": {"content": {"probability": 0.5}}}]},
        ):
            with (
                patch("hypothesis_lab.local_inference._request", return_value=content),
                self.subTest(content=content),
                self.assertRaises(ValueError),
            ):
                call_llm(connection(), "x")
        for budget in (0, 2049):
            with (
                patch("hypothesis_lab.local_inference._request") as request,
                self.assertRaises(ValueError),
            ):
                call_llm(connection(max_tokens=budget), "x")
            request.assert_not_called()

    def test_reported_token_counts_require_nonnegative_integer_metadata(self):
        for value in (-1, True, 1.5, "8", 8.0):
            with self.subTest(value=value):
                response = {
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {"completion_tokens": value},
                }
                with (
                    patch("hypothesis_lab.local_inference._request", return_value=response),
                    self.assertRaisesRegex(ValueError, "nonnegative integers"),
                ):
                    call_llm(connection(), "x")
                with self.assertRaises(ValueError):
                    extract_signal({"completion_tokens": value}, {"signal": "completion_tokens"})
        self.assertEqual(
            extract_signal({"completion_tokens": 0}, {"signal": "completion_tokens"}), 0
        )

    def test_endpoint_target_horizon_ground_truth_and_prompts_are_explicit(self):
        bars, rows = data()
        prompts = []

        def local_model(config, prompt, credential):
            prompts.append(prompt)
            return {"text": '{"probability":0.75}', "completion_tokens": 8}

        config = {
            "feature_names": ["traffic"],
            "target_field": "traffic",
            "target_type": "increase",
            "horizon": 2,
            "evaluation_start_index": 16,
        }
        selected = connection(
            prompt="Predict whether {target} increases over {horizon} bars from {features}"
        )
        with patch("hypothesis_lab.local_inference.call_llm", side_effect=local_model):
            result = run_endpoint_model(bars, rows, config, selected)
        records = result["inference_decisions"]
        self.assertEqual([record["actual"] for record in records], [1.0, 1.0, None])
        self.assertEqual([record["forecast_correct"] for record in records], [True, True, None])
        self.assertTrue(records[0]["forecast_market_discrepancy"])
        self.assertFalse(records[-1]["forecast_market_discrepancy"])
        self.assertEqual(
            records[0]["target_label_available_at"],
            (bars[18].timestamp + timedelta(days=1)).isoformat(),
        )
        self.assertEqual(result["test"]["rows"], 2)
        self.assertAlmostEqual(result["test"]["log_loss"], -math.log(0.75))
        self.assertEqual(result["test"]["accuracy"], 1)
        self.assertIn("traffic increases over 2 bars", prompts[0])
        self.assertNotIn("{target}", prompts[0])
        self.assertNotIn("{horizon}", prompts[0])

    def test_numeric_endpoint_level_and_return_targets_have_residual_diagnostics(self):
        bars, rows = data()
        rows[17]["traffic"] = 10.0
        rows[18]["traffic"] = 15.0
        rows[19]["traffic"] = 0.0
        config = {
            "feature_names": ["traffic"],
            "target_field": "traffic",
            "target_type": "return",
            "horizon": 1,
            "evaluation_start_index": 17,
        }
        selected = connection(kind="tabular", output_kind="prediction", output_field="predictions")
        with patch(
            "hypothesis_lab.local_inference._request", return_value={"predictions": [0.5, -1]}
        ):
            result = run_endpoint_model(bars, rows, config, selected)
        self.assertEqual([record["actual"] for record in result["predictions"]], [0.5, -1])
        self.assertEqual(result["test"]["mse"], 0)
        self.assertNotIn("log_loss", result["test"])
        self.assertTrue(all(record["forecast_correct"] is None for record in result["predictions"]))
        config["target_type"] = "level"
        with patch(
            "hypothesis_lab.local_inference._request", return_value={"predictions": [15, 0]}
        ):
            result = run_endpoint_model(bars, rows, config, selected)
        self.assertEqual(result["test"]["mae"], 0)
        self.assertEqual([record["actual"] for record in result["predictions"]], [15, 0])

    def test_mismatched_rows_unknown_targets_and_nonfinite_inputs_fail_before_requests(self):
        bars, rows = data()
        selected = connection()
        cases = [
            (rows[:-1], {"feature_names": ["traffic"]}),
            (rows, {"feature_names": ["traffic"], "target_field": "absent"}),
            (rows, {"feature_names": ["traffic"], "horizon": 1.5}),
        ]
        for features, config in cases:
            with (
                patch("hypothesis_lab.local_inference.call_llm") as mocked,
                self.subTest(config=config),
                self.assertRaises(ValueError),
            ):
                run_endpoint_model(bars, features, config, selected)
            mocked.assert_not_called()
        rows[-2]["traffic"] = float("nan")
        with (
            patch("hypothesis_lab.local_inference.call_llm") as mocked,
            self.assertRaises(ValueError),
        ):
            run_endpoint_model(bars, rows, {"feature_names": ["traffic"]}, selected)
        mocked.assert_not_called()

    def test_model_plan_metadata_requires_lists_of_strings(self):
        for entries in ("one string", None, [1], {"field": "value"}):
            with (
                self.subTest(entries=entries),
                patch(
                    "hypothesis_lab.local_inference.call_llm",
                    return_value={
                        "text": json.dumps(
                            {"search_terms": "traffic count", "required_measurements": entries}
                        )
                    },
                ),
                self.assertRaisesRegex(ValueError, "lists of strings"),
            ):
                llm_plan("traffic", connection())

    def test_public_connection_is_allowlisted_and_echoed_credentials_are_redacted(self):
        credential = 'private"session-value'
        selected = connection(
            token=credential, password=credential, api_key=credential, authorization=credential
        )
        public = public_connection(selected)
        self.assertEqual(
            set(public),
            set(selected).intersection(
                {
                    "kind",
                    "endpoint",
                    "model",
                    "allow_remote",
                    "prompt",
                    "signal",
                    "output_field",
                    "phrase",
                    "output_kind",
                    "max_calls",
                    "max_tokens",
                    "temperature",
                }
            ),
        )
        self.assertNotIn(credential, json.dumps(public))
        response = {
            "choices": [
                {"message": {"content": json.dumps({"echo": credential, "probability": 0.75})}}
            ],
            "usage": {"completion_tokens": 8},
            "model": credential,
        }
        with patch("hypothesis_lab.local_inference._request", return_value=response):
            result = call_llm(selected, "x", credential)
        self.assertNotIn(credential, result["text"])
        self.assertNotIn(json.dumps(credential)[1:-1], result["text"])
        self.assertEqual(result["reported_model"], "[redacted]")
        self.assertEqual(extract_signal(result, {"signal": "json_field"}), 0.75)


if __name__ == "__main__":
    unittest.main()
