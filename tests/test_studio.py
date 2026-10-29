"""Local HTTP integration for broad inputs, signal interpretation and trading windows."""

import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from hypothesis_lab.features import demo_content
from hypothesis_lab.research import rerun_payload, run_experiment
from hypothesis_lab.server import make_server
from hypothesis_lab.strategies import preset


class StudioResearchTests(unittest.TestCase):
    def test_algorithm_custom_signal_window_clock_and_rerun(self):
        body = {
            "mode": "algorithm",
            "feature_data": demo_content(),
            "period": {"last_bars": 25},
            "algorithm": {
                "signals": [
                    {"name": "growth", "expression": "pct_change(col('ice_cream_sales'), 7)"}
                ],
                "entry": "growth > -100",
                "exit": "growth < -100",
                "sizing": "cash",
                "amount": 100,
            },
            "execution": {
                "fee_bps": 10,
                "fixed_fee": 1,
                "spread_bps": 10,
                "slippage_bps": 5,
                "latency_ms": 10,
            },
        }
        run = run_experiment(body, persist=False)
        self.assertEqual(run["period"]["bars"], 25)
        self.assertEqual(run["algorithm"]["entry_matches"], 25)
        self.assertEqual(len(run["strategy"]["equity"]), 25)
        self.assertEqual(run["strategy"]["fills"][0]["filled_at"], run["market"][2]["timestamp"])
        self.assertGreater(run["strategy"]["fills"][0]["fee"], 1)
        self.assertEqual(run_experiment(rerun_payload(run), persist=False)["id"], run["id"])

    def test_buyhold_first_active_decision_and_date_identity(self):
        first = run_experiment(
            {"strategy": preset("buy_hold"), "period": {"last_bars": 20}}, persist=False
        )
        second = run_experiment(
            {"strategy": preset("buy_hold"), "period": {"last_bars": 25}}, persist=False
        )
        self.assertEqual(len(first["strategy"]["fills"]), 1)
        self.assertEqual(
            first["strategy"]["fills"][0]["filled_at"], first["market"][1]["timestamp"]
        )
        self.assertNotEqual(first["dataset"]["identity"], second["dataset"]["identity"])
        self.assertEqual(first["strategy"]["metrics"], first["benchmark"]["metrics"])


class StudioHTTPTests(unittest.TestCase):
    def setUp(self):
        directory = Path(__file__).resolve().parents[1] / "work" / "studio-checks"
        directory.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=directory)
        self.env = patch.dict(os.environ, {"HYPOTHESIS_LAB_HOME": self.temp.name})
        self.env.start()
        self.server = make_server(0)
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        self.thread.start()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.server.shutdown()
        self.thread.join(3)
        self.server.server_close()
        self.env.stop()
        self.temp.cleanup()

    def request(self, path, body=None):
        port = self.server.server_port
        client = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
        try:
            client.request(
                "GET" if body is None else "POST",
                path,
                body=None if body is None else json.dumps(body),
                headers={
                    "Content-Type": "application/json",
                    "Origin": f"http://127.0.0.1:{port}",
                    "X-Lab-Token": self.server.token,
                },
            )
            response = client.getresponse()
            raw = response.read()
            return response.status, json.loads(raw) if response.getheader(
                "Content-Type", ""
            ).startswith("application/json") else raw
        finally:
            client.close()

    def test_plain_algorithm_plan_preview_run_export_remain_session_only(self):
        status, plan = self.request(
            "/api/algorithm/plan",
            {
                "description": "Buy when ice cream sales > 100; sell when traffic count < 20",
                "fields": ["ice_cream_sales", "traffic_count"],
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(plan["executable"])
        body = {
            "algorithm": plan["draft"],
            "feature_data": demo_content(),
            "period": {"last_bars": 15},
        }
        status, preview = self.request("/api/algorithm/preview", body)
        self.assertEqual(status, 200, preview)
        self.assertEqual(len(preview["preview"]), 15)
        self.assertEqual(self.request("/api/history")[1], [])
        status, run = self.request("/api/run", {**body, "mode": "algorithm"})
        self.assertEqual(status, 200, run)
        self.assertEqual(len(run["market"]), 15)
        self.assertEqual(self.request("/api/rerun", {"id": run["id"]})[1]["id"], run["id"])
        self.assertFalse(list(Path(self.temp.name).rglob("*.json")))

    def test_model_plan_is_validated_and_executable_code_rejected(self):
        request = {
            "description": "Buy when traffic is high and sell when low",
            "fields": ["traffic"],
            "connection": {"kind": "llm", "endpoint": "http://127.0.0.1:11434/v1", "model": "mine"},
        }
        with patch(
            "hypothesis_lab.local_inference.call_llm",
            return_value={
                "text": json.dumps(
                    {"entry": "col('traffic') > 10", "exit": "col('traffic') < 5", "signals": []}
                )
            },
        ):
            status, plan = self.request("/api/algorithm/plan", request)
            self.assertEqual(status, 200, plan)
            self.assertTrue(plan["executable"])
        with patch(
            "hypothesis_lab.local_inference.call_llm",
            return_value={"text": json.dumps({"entry": "__import__('os').system('bad')"})},
        ):
            self.assertEqual(self.request("/api/algorithm/plan", request)[0], 400)

    def test_cost_profiles_separate_official_fee_evidence_from_assumptions(self):
        status, value = self.request("/api/execution/profiles")
        self.assertEqual(status, 200)
        official = [
            item
            for item in value["profiles"]
            if item["fee_evidence"]["kind"] == "official_schedule_snapshot"
        ]
        self.assertGreaterEqual(len(official), 3)
        for item in official:
            self.assertTrue(item["sources"])
            self.assertTrue(item["assumptions"])
            self.assertEqual(item["execution"]["fee_bps"], item["fee_evidence"]["taker_bps"])
