"""Real loopback service contracts and offline transport/privacy rejection cases."""

import io
import json
import socket
import threading
import unittest
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from hypothesis_lab import compute
from hypothesis_lab.features import read_records
from hypothesis_lab.local_inference import _request as prediction_request


class UserService(BaseHTTPRequestHandler):
    requests = []
    override = None
    probability = None

    def log_message(self, *args):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        request = json.loads(body)
        type(self).requests.append(
            {"path": self.path, "body": request, "authorization": self.headers.get("Authorization")}
        )
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header(
                "Location", f"http://127.0.0.1:{self.server.server_port}/wrong-service"
            )
            self.end_headers()
            return
        if self.path == "/denied":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"SENSITIVE_RESPONSE_BODY")
            return
        if self.path == "/predict":
            result = {"predictions": [self.probability for _ in request["features"]]}
        elif type(self).override is not None:
            override = type(self).override
            result = override(request) if callable(override) else override
        else:
            result = self.compute(request)
        raw = result if isinstance(result, bytes) else json.dumps(result).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def compute(self, request):
        task = request["task"]
        result = {
            "schema": compute.SCHEMA,
            "status": "complete",
            "operation": request["operation"],
            "task": task,
        }
        if request["operation"] == "train":
            # A tiny actual service-side fit: empirical prevalence of the declared
            # future condition. No app framework/model weight is involved.
            rows = read_records(request["input"]["content"], request["input"]["format"])
            horizon = task["horizon"]
            labels = [rows[i + horizon]["count"] > 3 for i in range(len(rows) - horizon)]
            type(self).probability = sum(labels) / len(labels)
            result["prediction"] = {
                "connection": {
                    "kind": "tabular",
                    "endpoint": f"http://127.0.0.1:{self.server.server_port}/predict",
                    "output_field": "predictions",
                    "output_kind": "probability",
                },
                "feature_names": ["count"],
                "trained_through": task["training_end"],
            }
            result["provenance"] = {
                "training_method": "Empirical prevalence fitted on the six selected synthetic training rows",
                "positive_labels": sum(labels),
                "labels": len(labels),
            }
        elif request["operation"] == "extract":
            known_path = request["input"].get("files", [{}])[0].get("path", "")
            result["dataset"] = {
                "records": [
                    {
                        "observed_at": "2023-01-01T00:00:00Z",
                        "count": 2,
                        "note": known_path,
                        "api_key": "UNRELATED_SECRET_FIELD",
                    }
                ],
                "mapping": {"field_columns": ["count"]},
            }
            result["warnings"] = ["Credential echo " + str(self.headers.get("Authorization", ""))]
            result["provenance"] = {
                "path": known_path,
                "description": "User-operated test extractor",
            }
        else:
            result["evaluation"] = {
                "metrics": {"accuracy": 0.8, "undefined": None},
                "rows": 5,
                "start": task["evaluation_start"],
                "end": task["evaluation_end"],
            }
        return result


def table_request(operation="train"):
    rows = [
        {
            "observed_at": (datetime(2023, 1, 1, tzinfo=UTC) + timedelta(days=i)).isoformat(),
            "count": i + 1,
        }
        for i in range(6)
    ]
    return {
        "operation": operation,
        "input": {"kind": "table", "format": "json", "content": json.dumps(rows)},
        "task": {
            "feature_names": ["count"],
            "target_type": "condition",
            "target_condition": 'col( "count" ) > 3',
            "horizon": 1,
            "training_end": "2023-01-06T00:00:00Z",
            "evaluation_start": "2024-01-01T00:00:00Z",
            "evaluation_end": "2024-02-01T00:00:00Z",
        },
        "options": {"device": "test-CPU", "seed": 42},
    }


class LocalComputeTests(unittest.TestCase):
    def setUp(self):
        UserService.requests, UserService.override, UserService.probability = [], None, None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), UserService)
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        self.thread.start()
        self.connection = {"endpoint": f"http://127.0.0.1:{self.server.server_port}/compute"}
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.server.shutdown()
        self.thread.join(timeout=3)
        self.server.server_close()

    def test_real_training_echoes_target_condition_and_reuses_the_numeric_prediction_service(self):
        result = compute.run_compute(self.connection, table_request(), "PRIVATE_SESSION_KEY")
        self.assertEqual(UserService.probability, 3 / 5)
        sent = UserService.requests[0]
        self.assertEqual(sent["body"]["task"]["target_condition"], 'col( "count" ) > 3')
        self.assertEqual(sent["body"]["task"]["horizon"], 1)
        self.assertEqual(sent["authorization"], "Bearer PRIVATE_SESSION_KEY")
        self.assertNotIn("PRIVATE_SESSION_KEY", json.dumps(sent["body"]))
        self.assertNotIn("PRIVATE_SESSION_KEY", json.dumps(result))
        self.assertEqual(result["model_config"]["target_type"], "condition")
        self.assertEqual(
            result["training_provenance"]["trained_through"], "2023-01-06T00:00:00+00:00"
        )
        response = prediction_request(
            result["prediction_connection"], {"feature_names": ["count"], "features": [[10], [2]]}
        )
        self.assertEqual(response["predictions"], [0.6, 0.6])
        self.assertNotIn("model", result)

    def test_manifest_is_metadata_only_no_file_read_and_private_paths_are_removed_from_results(
        self,
    ):
        path = "D:\\Private Research\\DOES_NOT_EXIST_secret_recording.wav"
        request = {
            "operation": "extract",
            "input": {
                "kind": "manifest",
                "files": [{"path": path, "role": "source", "media_type": "audio/wav"}],
            },
            "task": {"description": "My service extracts a declared event count"},
        }
        with patch(
            "builtins.open", side_effect=AssertionError("The app must not read a manifest file")
        ):
            result = compute.run_compute(self.connection, request, "SESSION_EXTRACT_KEY")
        self.assertEqual(UserService.requests[0]["body"]["input"]["files"][0]["path"], path)
        self.assertEqual(
            result["input_summary"], {"kind": "manifest", "files": 1, "contents_uploaded": False}
        )
        for secret in (path, "SESSION_EXTRACT_KEY", "UNRELATED_SECRET_FIELD"):
            self.assertNotIn(secret, json.dumps(result))
        record = result["dataset"]["records"][0]
        self.assertEqual(record["note"], "[redacted]")
        self.assertEqual(record["available_at"], result["provenance"]["acquired_at"])
        self.assertTrue(result["dataset"]["warnings"])
        self.assertEqual(result["dataset"]["mapping"]["availability_mode"], "column")

    def test_real_evaluation_accepts_finite_metrics_and_labels_them_service_reported(self):
        result = compute.run_compute(self.connection, table_request("evaluate"))
        self.assertEqual(result["evaluation"]["metrics"], {"accuracy": 0.8, "undefined": None})
        self.assertIn("not independently", result["evaluation"]["status"])
        self.assertEqual(result["evaluation"]["rows"], 5)

    def test_short_service_credentials_do_not_corrupt_legitimate_numeric_timestamps(self):
        result = compute.run_compute(self.connection, table_request(), "1")
        self.assertEqual(UserService.requests[0]["authorization"], "Bearer 1")
        self.assertEqual(
            result["training_provenance"]["trained_through"], "2023-01-06T00:00:00+00:00"
        )

    def test_real_redirect_refused_without_forwarding_credential_or_manifest(self):
        request = {
            "operation": "extract",
            "input": {
                "kind": "manifest",
                "files": [{"path": "/private/data/file.parquet", "role": "source"}],
            },
        }
        with self.assertRaisesRegex(compute.ComputeError, "not forwarded"):
            compute.run_compute(
                {"endpoint": self.connection["endpoint"].replace("/compute", "/redirect")},
                request,
                "SECRET_REDIRECT_KEY",
            )
        self.assertEqual([item["path"] for item in UserService.requests], ["/redirect"])

    def test_http_errors_never_include_service_body_or_session_credential(self):
        with self.assertRaises(compute.ComputeError) as error:
            compute.run_compute(
                {"endpoint": self.connection["endpoint"].replace("/compute", "/denied")},
                table_request(),
                "SECRET_ERROR_KEY",
            )
        self.assertNotIn("SENSITIVE_RESPONSE_BODY", str(error.exception))
        self.assertNotIn("SECRET_ERROR_KEY", str(error.exception))
        self.assertIn("HTTP 401", str(error.exception))

    def test_changed_target_or_opaque_model_or_running_job_is_not_an_accepted_result(self):
        for change in (
            {"task": {"target_type": "level"}},
            {"python_code": "do_work()"},
            {"status": "running", "job_id": "123"},
        ):

            def reply(request):
                return {
                    "schema": compute.SCHEMA,
                    "status": "complete",
                    "operation": "train",
                    "task": request["task"],
                    **change,
                }

            UserService.override = reply
            with self.subTest(change=change), self.assertRaises(compute.ComputeError):
                compute.run_compute(self.connection, table_request())

    def test_duplicate_nonfinite_and_nonobject_json_responses_reject(self):
        for raw in (
            b"{}",
            b"[]",
            b'{"status":"complete","status":"complete"}',
            b'{"value":NaN}',
            b'{"value":Infinity}',
        ):
            UserService.override = raw
            with self.subTest(raw=raw), self.assertRaises(compute.ComputeError):
                compute.run_compute(self.connection, table_request())

    def test_bad_availability_timestamps_and_historical_lag_override_reject(self):
        for dataset in (
            {"records": [{"observed_at": "2024-01-01", "count": 2}]},
            {
                "records": [
                    {
                        "observed_at": "2024-01-02T00:00:00Z",
                        "available_at": "2024-01-01T00:00:00Z",
                        "count": 2,
                    }
                ]
            },
            {
                "records": [{"observed_at": "2024-01-01T00:00:00Z", "count": 2}],
                "mapping": {"availability_mode": "lag", "availability_lag_hours": 0},
            },
        ):
            UserService.override = lambda request: {
                "schema": compute.SCHEMA,
                "status": "complete",
                "operation": "extract",
                "task": request["task"],
                "dataset": dataset,
            }
            with self.subTest(dataset=dataset), self.assertRaises(compute.ComputeError):
                compute.run_compute(
                    self.connection, {"operation": "extract", "input": table_request()["input"]}
                )


class ComputeValidation(unittest.TestCase):
    def test_authorized_remote_inline_table_is_explicit_and_local_path_aliases_are_redacted(self):
        request = {
            "operation": "extract",
            "input": {"kind": "table", "format": "ndjson", "content": '{"count":2}\n'},
            "task": {},
        }
        response = {
            "schema": compute.SCHEMA,
            "status": "complete",
            "operation": "extract",
            "task": {},
            "dataset": {
                "records": [
                    {
                        "observed_at": "2023-01-01T00:00:00Z",
                        "transcript": "A private event description",
                    }
                ]
            },
        }
        with patch.object(compute, "_request", return_value=response) as send:
            result = compute.run_compute(
                {"endpoint": "https://example.org/compute", "allow_remote": True}, request
            )
        self.assertEqual(send.call_args.args[1]["input"]["format"], "ndjson")
        self.assertEqual(result["input_summary"]["contents_uploaded"], True)
        self.assertEqual(result["dataset"]["inspection"]["generated_fields"], [])
        cleaned = compute._clean(
            {"note": "D:/PRIVATE/Research/data.WAV", "model_path": "private"},
            None,
            ["d:\\private\\research\\data.wav"],
        )
        self.assertEqual(cleaned, {"note": "[redacted]"})

    def test_manifest_validation_never_reads_unsupported_binary_or_accepts_ambiguous_paths(self):
        for path in (
            "relative/data.h5",
            "https://example.org/raw.bin",
            "\\\\host\\share\\data.hdf",
            "file:///private/data.h5",
            "D:relative.bin",
        ):
            with self.subTest(path=path), self.assertRaises(compute.ComputeError):
                compute._input(
                    {"kind": "manifest", "files": [{"path": path, "role": "source"}]}, True
                )
        with patch("builtins.open", side_effect=AssertionError("No implicit file read")):
            source, paths, summary = compute._input(
                {
                    "kind": "manifest",
                    "files": [
                        {
                            "path": "/my/private/imagery.HDF",
                            "role": "source",
                            "media_type": "application/x-hdf",
                        }
                    ],
                },
                True,
            )
        self.assertEqual(paths, ["/my/private/imagery.HDF"])
        self.assertEqual(source["files"][0]["media_type"], "application/x-hdf")
        self.assertFalse(summary["contents_uploaded"])

    def test_remote_opt_in_never_authorizes_local_paths_or_private_addresses(self):
        manifest = {
            "operation": "extract",
            "input": {
                "kind": "manifest",
                "files": [{"path": "D:\\private\\data.hdf", "role": "source"}],
            },
        }
        with patch.object(compute, "_request") as send:
            for connection in (
                {"endpoint": "https://example.org/compute"},
                {"endpoint": "https://example.org/compute", "allow_remote": True},
                {"endpoint": "http://example.org/compute", "allow_remote": True},
                {"endpoint": "https://169.254.169.254/compute", "allow_remote": True},
                {"endpoint": "https://127.0.0.2/compute", "allow_remote": True},
            ):
                with self.subTest(connection=connection), self.assertRaises(compute.ComputeError):
                    compute.run_compute(connection, manifest)
            send.assert_not_called()
        for field, value in (
            ("options", {"model_path": "D:\\private\\weights"}),
            (
                "input",
                {
                    "kind": "table",
                    "format": "json",
                    "content": '[{"file_path":"/private/data.wav"}]',
                },
            ),
        ):
            request = table_request()
            request[field] = value
            with (
                self.subTest(field=field),
                patch.object(compute, "_request") as send,
                self.assertRaises(compute.ComputeError),
            ):
                compute.run_compute(
                    {"endpoint": "https://example.org/compute", "allow_remote": True}, request
                )
            send.assert_not_called()

    def test_invalid_task_conditions_and_overlap_are_rejected_before_any_request(self):
        changes = [
            {"training_end": None},
            {"horizon": True},
            {"horizon": 1.5},
            {"target_condition": {"operator": ">", "value": 3}},
            {"target_condition": '__import__("os").system("BAD")'},
            {"evaluation_start": "2022-01-01T00:00:00Z"},
            {"target_type": "custom"},
        ]
        for change in changes:
            request = table_request()
            request["task"].update(change)
            with (
                self.subTest(change=change),
                patch.object(compute, "_request") as send,
                self.assertRaises(compute.ComputeError),
            ):
                compute.run_compute({"endpoint": "http://127.0.0.1:1/compute"}, request)
            send.assert_not_called()
        with self.assertRaises(compute.ComputeError):
            compute.run_compute(
                {"endpoint": "http://localhost:1"},
                {**table_request(), "options": {"api_key": "PRIVATE"}},
            )

    def test_returned_model_boundaries_origins_and_output_semantics_are_strict(self):
        connection = {"endpoint": "http://127.0.0.1:8767/compute"}
        request = table_request()
        task = compute._task(request["task"], "train")
        prediction = {
            "connection": {"kind": "tabular", "endpoint": "http://127.0.0.1:8767/predict"},
            "feature_names": ["count"],
            "trained_through": task["training_end"],
        }
        for change in (
            {"trained_through": "2024-01-01T00:00:00Z"},
            {"feature_names": ["wrong"]},
            {"connection": {"kind": "tabular", "endpoint": "http://127.0.0.1:8768/predict"}},
            {
                "connection": {
                    "kind": "tabular",
                    "endpoint": "http://127.0.0.1:8767/predict",
                    "output_kind": "prediction",
                }
            },
        ):
            with self.subTest(change=change), self.assertRaises(compute.ComputeError):
                compute._prediction({**prediction, **change}, connection, task)

    def test_metric_booleans_strings_nonfinite_and_outside_windows_reject(self):
        task = compute._task(table_request()["task"], "evaluate")
        value = {
            "metrics": {"mse": 1},
            "rows": 2,
            "start": task["evaluation_start"],
            "end": task["evaluation_end"],
        }
        for change in (
            {"metrics": {"mse": True}},
            {"metrics": {"mse": "0.2"}},
            {"metrics": {"mse": float("inf")}},
            {"rows": 1.5},
            {"start": "2023-12-31T00:00:00Z"},
            {"end": "2025-01-01T00:00:00Z"},
        ):
            with self.subTest(change=change), self.assertRaises(compute.ComputeError):
                compute._evaluation({**value, **change}, task)

    def test_localhost_dns_cannot_be_rebound_to_a_nonloopback_address(self):
        answers = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 1)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 1)),
        ]
        with (
            patch.object(compute.socket, "getaddrinfo", return_value=answers),
            patch.object(compute.socket, "create_connection") as connect,
            self.assertRaises(compute.ComputeError),
        ):
            compute._loopback_socket("localhost", 1, 1)
        connect.assert_not_called()

    def test_transport_bounds_timeout_invalid_json_and_proxy_settings(self):
        calls = []

        class Opener:
            def open(self, request, timeout):
                calls.append((request, timeout))
                return io.BytesIO(b'{"ok":1}')

        with patch.object(compute.urllib.request, "build_opener", return_value=Opener()) as build:
            self.assertEqual(
                compute._request(
                    {
                        "endpoint": "https://example.org/compute",
                        "allow_remote": True,
                        "timeout_seconds": 5,
                    },
                    {"schema": compute.SCHEMA},
                    None,
                ),
                {"ok": 1},
            )
        self.assertEqual(calls[0][1], 5)
        handlers = build.call_args.args
        self.assertTrue(
            any(isinstance(handler, compute._PinnedHTTPSHandler) for handler in handlers)
        )
        self.assertTrue(
            any(
                isinstance(handler, compute.urllib.request.ProxyHandler) and handler.proxies == {}
                for handler in handlers
            )
        )
        with patch.object(compute.urllib.request, "build_opener") as build:
            build.return_value.open.return_value = io.BytesIO(
                b"x" * (compute.MAX_RESPONSE_BYTES + 1)
            )
            with self.assertRaisesRegex(compute.ComputeError, "4 MB"):
                compute._request({"endpoint": "http://localhost:1"}, {}, None)
        with patch.object(compute.urllib.request, "build_opener") as build:
            build.return_value.open.side_effect = TimeoutError("PRIVATE_TIMEOUT_VALUE")
            with self.assertRaises(compute.ComputeError) as error:
                compute._request({"endpoint": "http://localhost:1"}, {}, None)
            self.assertNotIn("PRIVATE_TIMEOUT_VALUE", str(error.exception))
        with (
            patch.object(compute.urllib.request, "build_opener") as build,
            self.assertRaisesRegex(compute.ComputeError, "6 MB"),
        ):
            compute._request(
                {"endpoint": "http://localhost:1"}, {"blob": "x" * compute.MAX_REQUEST_BYTES}, None
            )
        build.assert_not_called()


if __name__ == "__main__":
    unittest.main()
