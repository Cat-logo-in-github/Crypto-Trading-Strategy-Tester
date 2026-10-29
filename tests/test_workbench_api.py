"""Real localhost checks for general discovery, session privacy and inference adapters."""

import http.client
import json
import os
import tempfile
import threading
import unittest
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from hypothesis_lab.data import Bar
from hypothesis_lab.features import demo_content
from hypothesis_lab.local_inference import call_llm, run_endpoint_model
from hypothesis_lab.server import make_server


class WorkbenchAPI(unittest.TestCase):
    def setUp(self):
        directory = Path(__file__).resolve().parents[1] / "work" / "api-checks"
        directory.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=directory)
        self.state = Path(self.temp.name)
        self.environment = patch.dict(os.environ, {"HYPOTHESIS_LAB_HOME": str(self.state)})
        self.environment.start()
        self.server = make_server(0)
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        self.thread.start()
        self.port = self.server.server_port
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.server.shutdown()
        self.thread.join(timeout=3)
        self.server.server_close()
        self.environment.stop()
        self.temp.cleanup()

    def request(self, path, body=None):
        client = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        headers = {
            "X-Lab-Token": self.server.token,
            "Origin": f"http://127.0.0.1:{self.port}",
            "Content-Type": "application/json",
        }
        try:
            client.request(
                "GET" if body is None else "POST",
                path,
                body=None if body is None else json.dumps(body).encode(),
                headers=headers,
            )
            response = client.getresponse()
            return response.status, json.loads(response.read())
        finally:
            client.close()

    def test_session_first_runs_opt_in_local_save_and_saved_history(self):
        status, result = self.request(
            "/api/run",
            {
                "strategy": {"name": "cash", "entry": {"left": "close", "op": "<", "right": 0}},
                "name": "session",
            },
        )
        self.assertEqual(status, 200)
        self.assertFalse(list(self.state.rglob("experiments/*.json")))
        self.assertEqual(self.request("/api/history")[1][0]["id"], result["id"])
        self.assertIn(
            "cash_after",
            self.request("/api/run", {"name": "saved", "persist_local": True})[1]["strategy"][
                "fills"
            ][0],
        )
        self.assertEqual(len(list((self.state / "experiments").glob("*.json"))), 1)
        self.server.session_runs.clear()
        self.assertEqual(self.request("/api/history")[1], [])
        saved = self.request("/api/history?include_saved=1")[1]
        self.assertEqual(len(saved), 1)
        self.assertEqual(self.request("/api/experiments/" + saved[0]["id"])[0], 200)
        self.assertEqual(self.request("/api/rerun", {"id": saved[0]["id"]})[0], 200)

    def test_arbitrary_data_rule_model_upload_and_export_routes(self):
        content = demo_content()
        status, info = self.request("/api/dataset/inspect", {"content": content, "format": "csv"})
        self.assertEqual(status, 200)
        status, spec = self.request(
            "/api/parse",
            {"text": "Buy $20 when ice cream sales > 120", "fields": info["generated_fields"]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(spec["entry"]["left"], "event:ice_cream_sales")
        payload = {
            "mode": "model",
            "feature_data": content,
            "feature_mapping": info["mapping"],
            "model_config": {
                "feature_names": ["merch_sales", "traffic_count"],
                "target_field": "merch_sales",
                "epochs": 8,
                "l2_candidates": [0.01],
            },
        }
        status, result = self.request("/api/run", payload)
        self.assertEqual(status, 200)
        self.assertEqual(result["model"]["model"]["family"], "logistic")
        self.assertTrue(result["diagnostics"]["inference_decisions"])
        self.assertTrue(
            all(0 <= row["prediction"] <= 1 for row in result["diagnostics"]["inference_decisions"])
        )
        artifact = {"format": "json", "model": result["model"]["model"]}
        self.assertEqual(self.request("/api/model/inspect", {"artifact": artifact})[0], 200)
        self.assertEqual(self.request("/api/run", {**payload, "pretrained": artifact})[0], 200)
        self.assertEqual(self.request("/api/rerun", {"id": result["id"]})[1]["id"], result["id"])
        self.assertEqual(len(result["ledger"]), len(result["strategy"]["equity"]))

    def test_data_plans_search_and_keyless_fetch_are_explicit_routes(self):
        status, plan = self.request(
            "/api/ideas/plan",
            {"query": "Buy when rubber duck sales rise", "fields": ["rubber_duck_sales"]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(plan["signals"][0]["candidate_fields"], ["rubber_duck_sales"])
        self.assertIn("Private", plan["data_requirements"][0]["private_data"])
        with patch(
            "hypothesis_lab.server.search_sources", return_value={"datasets": [], "warnings": []}
        ) as search:
            self.assertEqual(self.request("/api/sources/search", {"query": "traffic"})[0], 200)
            search.assert_called_once_with("traffic", "socrata")
        with patch(
            "hypothesis_lab.server.fetch_source", return_value={"format": "json", "content": "[]"}
        ) as fetch:
            self.assertEqual(
                self.request("/api/sources/fetch", {"config": {"id": "worldbank"}})[0], 200
            )
            fetch.assert_called_once_with({"id": "worldbank"}, None)

    def test_dataset_envelope_accepts_escaped_large_tables_but_bounds_preview(self):
        content = (
            "observed_at,available_at,count,note\n2024-01-01T00:00:00Z,2024-01-01T00:00:00Z,1,"
            + "x" * 3_100_000
        )
        status, info = self.request("/api/dataset/inspect", {"content": content, "format": "csv"})
        self.assertEqual(status, 200)
        self.assertEqual(len(info["preview"][0]["note"]), 500)

    def test_map_own_api_table_to_actual_market_prices(self):
        rows = [
            {"t": 1704067200000, "o": 10, "h": 12, "l": 9, "c": 11, "v": 7},
            {"t": 1704153600000, "o": 11, "h": 13, "l": 10, "c": 12, "v": 8},
        ]
        payload = {
            "content": json.dumps(rows),
            "format": "json",
            "mapping": {
                "timestamp_column": "t",
                "timestamp_format": "unix_milliseconds",
                "open": "o",
                "high": "h",
                "low": "l",
                "close": "c",
                "volume": "v",
            },
        }
        status, mapped = self.request("/api/dataset/market", payload)
        self.assertEqual(status, 200)
        self.assertEqual(mapped["rows"], 2)
        self.assertEqual(mapped["start"], "2024-01-01T00:00:00+00:00")
        self.assertIn(",10.0,12.0,9.0,11.0,7.0", mapped["market_csv"])
        del payload["mapping"]["close"]
        self.assertEqual(self.request("/api/dataset/market", payload)[0], 400)
        self.assertFalse(list(self.state.rglob("*.json")))


class CompletionHandler(BaseHTTPRequestHandler):
    requests = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.requests.append(
            {"path": self.path, "body": payload, "authorization": self.headers.get("Authorization")}
        )
        data = json.dumps(
            {
                "model": "local-protocol-fixture",
                "choices": [{"message": {"content": '{"probability":0.75}'}}],
                "usage": {"completion_tokens": 13, "prompt_tokens": 20, "total_tokens": 33},
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class LocalProtocolTests(unittest.TestCase):
    def setUp(self):
        CompletionHandler.requests = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), CompletionHandler)
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        self.thread.start()
        self.connection = {
            "endpoint": f"http://127.0.0.1:{self.server.server_port}/v1",
            "model": "local-fixture",
            "max_tokens": 20,
        }

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=3)
        self.server.server_close()

    def test_real_local_chat_protocol_and_session_authorization(self):
        result = call_llm(self.connection, "A synthetic test prompt", "LOCAL_TEST_CREDENTIAL")
        self.assertEqual(result["completion_tokens"], 13)
        self.assertEqual(CompletionHandler.requests[0]["path"], "/v1/chat/completions")
        self.assertEqual(
            CompletionHandler.requests[0]["authorization"], "Bearer LOCAL_TEST_CREDENTIAL"
        )
        self.assertEqual(
            CompletionHandler.requests[0]["body"]["messages"][0]["content"],
            "A synthetic test prompt",
        )

    def test_real_local_token_signal_replay_has_labels_fills_and_no_exported_key(self):
        bars = [
            Bar(datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i), 100, 100, 100, 100)
            for i in range(11)
        ]
        rows = [{"ice_cream_sales": float(i + 1)} for i in range(11)]
        result = run_endpoint_model(
            bars,
            rows,
            {
                "feature_names": ["ice_cream_sales"],
                "target_field": "ice_cream_sales",
                "target_type": "level",
                "evaluation_start_index": 8,
                "decision": {"threshold": 10},
            },
            {
                **self.connection,
                "signal": "completion_tokens",
                "output_kind": "prediction",
                "max_calls": 2,
                "prompt": "Features {features}; target {target}; horizon {horizon}.",
            },
            "LOCAL_TEST_CREDENTIAL",
        )
        self.assertEqual(len(CompletionHandler.requests), 2)
        self.assertEqual([r["prediction"] for r in result["predictions"]], [13, 13])
        self.assertEqual([r["actual"] for r in result["predictions"]], [10, 11])
        self.assertEqual(result["test"]["mse"], 6.5)
        self.assertEqual(len(result["backtest"]["fills"]), 1)
        self.assertNotIn("LOCAL_TEST_CREDENTIAL", json.dumps(result))
