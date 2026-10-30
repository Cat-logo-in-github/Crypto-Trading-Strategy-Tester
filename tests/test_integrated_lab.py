"""Real local UI/API tests for scenario, training and execution-backend integration."""

import http.client
import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch

from hypothesis_lab.portfolio_templates import catalogue, template_payload
from hypothesis_lab.research import rerun_payload, run_experiment
from hypothesis_lab.server import make_server
from hypothesis_lab.validation import uncertainty


class IntegratedContracts(unittest.TestCase):
    def test_all_requested_contract_templates_are_runnable_exportable_and_replayable(self):
        for item in catalogue():
            with self.subTest(template=item["id"]):
                result = run_experiment(template_payload(item["id"]), persist=False)
                self.assertTrue(result["strategy"]["fills"])
                self.assertGreater(result["portfolio"]["coverage"]["quotes"], 0)
                self.assertEqual(
                    result["strategy"],
                    run_experiment(rerun_payload(result), persist=False)["strategy"],
                )
                self.assertEqual(
                    result["id"], run_experiment(rerun_payload(result), persist=False)["id"]
                )
                self.assertIn("cash", result["benchmark"]["label"].lower())
                json.dumps(result, allow_nan=False)

    def test_quote_replay_is_used_for_rule_model_style_intents_and_reruns(self):
        body = {
            "mode": "algorithm",
            "market_csv": "timestamp,open,high,low,close,volume\n2024-01-01T00:00:00Z,100,101,99,100,100\n2024-01-01T00:01:00Z,100,101,99,100,100\n2024-01-01T00:02:00Z,100,101,99,100,100\n",
            "algorithm": {"entry": "market.close > 0", "sizing": "target", "weight": 1},
            "execution": {"initial_cash": 1000, "fee_bps": 0, "slippage_bps": 0, "bar_seconds": 60},
            "execution_replay": {
                "instrument": "TST",
                "max_quote_age_ms": 2000,
                "participation_rate": 1,
                "records": [
                    {
                        "timestamp": "2024-01-01T00:00:59Z",
                        "instrument": "TST",
                        "type": "quote",
                        "bid": 99,
                        "ask": 100,
                        "bid_size": 100,
                        "ask_size": 100,
                    }
                ],
            },
        }
        result = run_experiment(body, persist=False)
        self.assertEqual(result["strategy"]["fills"][0]["price"], 100)
        self.assertIn("replay", result["strategy"])
        self.assertEqual(result["id"], run_experiment(rerun_payload(result), persist=False)["id"])
        bad = {**body, "portfolio": {"legs": {"TST": 1}}}
        with self.assertRaisesRegex(ValueError, "Choose single"):
            run_experiment(bad, persist=False)

    def test_uncertainty_is_deterministic_time_paired_and_refuses_false_alignment(self):
        def ledger(values):
            return {"equity": [{"timestamp": str(i), "equity": x} for i, x in enumerate(values)]}

        a = ledger([100 + i for i in range(80)])
        b = ledger([100] * 80)
        first = uncertainty(a, b)
        self.assertEqual(first, uncertainty(a, b))
        self.assertGreater(first["mean_excess_95pct_interval"][0], 0)
        self.assertEqual(uncertainty(ledger([100, 101]), ledger([100, 100]))["bars"], 1)
        self.assertIsNone(
            uncertainty(ledger([100, 101]), ledger([100, 100]))["mean_excess_95pct_interval"]
        )
        b["equity"][0]["timestamp"] = "different"
        with self.assertRaises(ValueError):
            uncertainty(a, b)


class LabHTTP(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"HYPOTHESIS_LAB_HOME": self.folder.name})
        self.env.start()
        self.server = make_server(0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.env.stop()
        self.folder.cleanup()

    def request(self, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        headers = {
            "Origin": f"http://127.0.0.1:{self.port}",
            "X-Lab-Token": self.server.token,
            "Content-Type": "application/json",
        }
        conn.request(
            "GET" if body is None else "POST",
            path,
            body=json.dumps(body) if body is not None else None,
            headers=headers,
        )
        response = conn.getresponse()
        raw = response.read()
        status = response.status
        conn.close()
        return status, json.loads(raw) if raw.startswith(b"{") else raw

    def test_ui_assets_catalogues_plain_language_and_contract_execution(self):
        for path in ["/lab.js", "/lab.css", "/portfolio-ui.js", "/portfolio-ui.css"]:
            self.assertEqual(self.request(path)[0], 200, path)
        code, public = self.request("/api/public-results")
        self.assertEqual(code, 200)
        self.assertEqual(len(public["trials"]), 5)
        self.assertIn("Actual public data", public["status"])
        code, listed = self.request("/api/scenarios")
        self.assertEqual(code, 200)
        self.assertEqual(len(listed["scenarios"]), 5)
        code, result = self.request(
            "/api/scenarios/run",
            {"id": "horror_library", "include_records": True, "include_controls": True},
        )
        self.assertEqual(code, 200, result)
        self.assertTrue(result["scenarios"][0]["run"]["strategy"]["fills"])
        code, listed = self.request("/api/portfolio/templates")
        self.assertEqual(len(listed["templates"]), 5)
        code, loaded = self.request("/api/portfolio/templates?id=funding_vampire")
        self.assertEqual(code, 200)
        code, result = self.request("/api/run", loaded["payload"])
        self.assertEqual(code, 200, result)
        self.assertTrue(result["portfolio"])
        self.assertGreater(result["summary"]["funding_cash"], 0)
        self.assertEqual(self.request("/api/compute", {"connection": {}, "request": {}})[0], 400)
        self.assertEqual(
            self.request(
                "/api/algorithm/plan",
                {
                    "description": "Buy $100 when horror share is above 0.35 and horror change is greater than 0; sell when horror share is below 0.3",
                    "fields": ["horror_share", "horror_change"],
                },
            )[1]["executable"],
            True,
        )
        self.assertFalse(list(__import__("pathlib").Path(self.folder.name).rglob("*.json")))
