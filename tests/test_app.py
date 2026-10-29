"""Offline provider, storage, research and real loopback HTTP integration checks."""

import http.client
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.error
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from hypothesis_lab import providers
from hypothesis_lab.data import fixtures, timestamp
from hypothesis_lab.research import events_csv, feature_search, rerun_payload, run_experiment
from hypothesis_lab.server import make_server
from hypothesis_lab.storage import (
    credential_status,
    list_experiments,
    load_credential,
    load_experiment,
    remove_credential,
    save_credential,
    save_experiment,
    state_dir,
)
from hypothesis_lab.strategies import preset


def mocked_response(value):
    raw = value if isinstance(value, bytes) else json.dumps(value).encode()
    return patch(
        "hypothesis_lab.providers.urllib.request.urlopen",
        side_effect=lambda *args, **kwargs: io.BytesIO(raw),
    )


def market_csv(count=12):
    start = datetime(2024, 1, 1, tzinfo=UTC)
    lines = ["timestamp,open,high,low,close,volume"]
    for index in range(count):
        price = 100 + index
        lines.append(
            f"{(start + timedelta(days=index)).isoformat()},{price},{price},{price},{price},100"
        )
    return "\n".join(lines)


class IsolatedState(unittest.TestCase):
    def setUp(self):
        temporary_root = Path(__file__).resolve().parents[1] / "work" / "test-state"
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(
            prefix="hypothesis-lab-tests-", dir=temporary_root
        )
        self.environment = patch.dict(os.environ, {"HYPOTHESIS_LAB_HOME": self.directory.name})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.addCleanup(self.directory.cleanup)

        # OS protection is verified separately with a subprocess deadline. These
        # unit/integration checks test the consent and ciphertext storage contract.
        def protect(raw, decrypt=False):
            if decrypt:
                if not raw.startswith(b"unit-test-protected:"):
                    raise ValueError("Invalid test ciphertext")
                return raw[len(b"unit-test-protected:") :]
            return b"unit-test-protected:" + raw

        self.protection = patch("hypothesis_lab.storage._protect", side_effect=protect)
        self.protection.start()
        self.addCleanup(self.protection.stop)


class ProviderTests(unittest.TestCase):
    def test_kraken_removes_uncommitted_row_and_labels_daily_snapshot(self):
        start = 1704067200
        rows = [
            [start, "10", "12", "9", "11", "10", "100", 1],
            [start + 86400, "11", "13", "10", "12", "11", "200", 1],
            [start + 172800, "999", "999", "999", "999", "999", "1", 1],
        ]
        with mocked_response(
            {"error": [], "result": {"XXBTZUSD": rows, "last": start + 172800}}
        ) as request:
            result = providers.kraken_snapshot()
        self.assertEqual(len(result["bars"]), 2)
        self.assertEqual(result["latest_close"], 12)
        self.assertEqual(result["bars"][0]["volume"], 100)
        self.assertEqual(result["kind"], "completed_daily_snapshot")
        self.assertEqual(timestamp(result["last_completed_at"]), datetime(2024, 1, 3, tzinfo=UTC))
        self.assertGreaterEqual(result["delay_seconds"], 0)
        self.assertTrue(any("not a real-time" in warning.lower() for warning in result["warnings"]))
        self.assertEqual(request.call_count, 1)

    def test_kraken_error_missing_data_and_malformed_rows_are_controlled(self):
        for value in (
            {"error": ["EGeneral:Temporary lockout"]},
            {"error": [], "result": {}},
            {"error": [], "result": {"XXBTZUSD": [[0], [1], [2]]}},
            {
                "error": [],
                "result": {
                    "XXBTZUSD": [
                        [0, 1, 1, 1, "nan", 1, 1],
                        [1, 1, 1, 1, 1, 1, 1],
                        [2, 1, 1, 1, 1, 1, 1],
                    ]
                },
            },
        ):
            with (
                self.subTest(value=value),
                mocked_response(value),
                self.assertRaises(providers.ProviderError),
            ):
                providers.kraken_snapshot()

    def test_provider_network_json_and_size_failures_do_not_echo_key(self):
        secret = "UNITTEST_PROVIDER_SECRET_42"
        errors = [
            urllib.error.URLError(f"https://provider.invalid/?apikey={secret}"),
            urllib.error.HTTPError(
                f"https://provider.invalid/?apikey={secret}", 401, secret, {}, None
            ),
            TimeoutError(secret),
        ]
        for failure in errors:
            with (
                self.subTest(failure=type(failure).__name__),
                patch("hypothesis_lab.providers.urllib.request.urlopen", side_effect=failure),
            ):
                with self.assertRaises(providers.ProviderError) as caught:
                    providers.alpha_vantage_test(secret)
                self.assertNotIn(secret, str(caught.exception))
        for raw in (b"not json", b"[]", b"x" * 2_000_001):
            with (
                self.subTest(size=len(raw)),
                mocked_response(raw),
                self.assertRaises(providers.ProviderError),
            ):
                providers.alpha_vantage_test(secret)

    def test_alpha_quote_quota_bad_value_and_success_are_honest_and_sanitized(self):
        key = "UNITTEST_PROVIDER_SECRET_42"
        with mocked_response(
            {"Global Quote": {"05. price": "123.45", "07. latest trading day": "2024-01-02"}}
        ):
            result = providers.alpha_vantage_test(key)
        self.assertEqual(result["price"], 123.45)
        self.assertEqual(result["kind"], "end_of_day_snapshot")
        self.assertIn("not a real-time", result["warning"])
        self.assertNotIn(key, json.dumps(result))
        for value in (
            {"Note": key},
            {"Information": key},
            {},
            {"Global Quote": {"05. price": key}},
            {"Global Quote": {"05. price": "nan"}},
            {"Global Quote": {"05. price": "-1"}},
        ):
            with self.subTest(value=value), mocked_response(value):
                with self.assertRaises(providers.ProviderError) as caught:
                    providers.alpha_vantage_test(key)
                self.assertNotIn(key, str(caught.exception))

    def test_revised_weather_is_available_only_at_acquisition(self):
        before = datetime.now(UTC)
        with mocked_response(
            {"daily": {"time": ["2024-01-01", "2024-01-02"], "temperature_2m_mean": [4.0, None]}}
        ):
            result = providers.open_meteo(25.2, 55.3, "2024-01-01", "2024-01-02")
        after = datetime.now(UTC)
        self.assertEqual(len(result["events"]), 1)
        event = result["events"][0]
        self.assertEqual(timestamp(event["observed_at"]), datetime(2024, 1, 2, tzinfo=UTC))
        self.assertLessEqual(before, timestamp(event["available_at"]))
        self.assertLessEqual(timestamp(event["available_at"]), after)
        self.assertEqual(event["location"], "25.2,55.3")
        self.assertEqual(result["kind"], "revised_historical_reanalysis")
        self.assertIn("CC BY 4.0", result["attribution"])
        self.assertTrue(any("NOT a point-in-time" in warning for warning in result["warnings"]))

    def test_weather_rejects_invalid_bounds_and_malformed_response(self):
        for arguments in (
            (91, 0, "2024-01-01", "2024-01-02"),
            (0, float("nan"), "2024-01-01", "2024-01-02"),
            (0, 0, "1939-01-01", "1939-01-02"),
            (0, 0, "2024-01-01", "2026-01-01"),
            (0, 0, "2099-01-01", "2099-01-02"),
        ):
            with (
                self.subTest(arguments=arguments),
                mocked_response({}) as request,
                self.assertRaises(ValueError),
            ):
                providers.open_meteo(*arguments)
            request.assert_not_called()
        with (
            mocked_response({"daily": {"time": ["2024-01-01"], "temperature_2m_mean": []}}),
            self.assertRaises(providers.ProviderError),
        ):
            providers.open_meteo(0, 0, "2024-01-01", "2024-01-02")


class StorageTests(IsolatedState):
    def test_settings_consent_protected_storage_roundtrip_and_removal(self):
        key = "LOCAL_UNITTEST_KEY_123"
        self.assertFalse(credential_status()["saved"])
        with self.assertRaises(ValueError):
            save_credential(key, consent=False)
        self.assertFalse((state_dir() / "credential.json").exists())
        save_credential(key, consent=True)
        self.assertTrue(credential_status()["saved"])
        self.assertEqual(load_credential(), key)
        saved = (state_dir() / "credential.json").read_text(encoding="utf-8")
        self.assertNotIn(key, saved)
        self.assertEqual(json.loads(saved)["protected"], os.name == "nt")
        self.assertNotIn(key, json.dumps(credential_status()))
        save_credential("UPDATED_KEY", consent=True)
        self.assertEqual(load_credential(), "UPDATED_KEY")
        remove_credential()
        remove_credential()
        self.assertFalse(credential_status()["saved"])
        with self.assertRaises(ValueError):
            load_credential()

    def test_settings_reject_invalid_key_without_echoing_it(self):
        for key in ("", "a" * 257, "key with spaces", "key/?apikey=secret"):
            with self.subTest(length=len(key)), self.assertRaises(ValueError) as caught:
                save_credential(key, consent=True)
            if key:
                self.assertNotIn(key, str(caught.exception))
        self.assertFalse(credential_status()["saved"])

    def test_experiment_atomic_save_identity_reload_history_and_traversal(self):
        record = {
            "schema_version": 1,
            "mode": "rules",
            "name": "A repeatable test",
            "summary": {"total_return": 0},
            "dataset": {"identity": "fixture"},
        }
        saved = save_experiment(record)
        again = save_experiment(record)
        self.assertEqual(saved["id"], again["id"])
        self.assertEqual(load_experiment(saved["id"]), again)
        self.assertEqual(len(list_experiments()), 1)
        self.assertEqual(list_experiments()[0]["name"], record["name"])
        self.assertIn("python", saved["runtime"])
        self.assertEqual(list((state_dir() / "experiments").glob("*.tmp")), [])
        for identity in ("../credential", "C:/private", "A" * 20, "abc"):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                load_experiment(identity)
        with self.assertRaises(ValueError):
            save_experiment({"unsafe": float("nan")})


class ResearchTests(IsolatedState):
    def test_default_offline_run_export_rerun_and_credentials_stay_separate(self):
        save_credential("PRIVATE_TEST_KEY_123", consent=True)
        first = run_experiment({"name": "weather run"})
        self.assertIn("synthetic", first["dataset"]["source"].lower())
        self.assertGreater(first["summary"]["trade_count"], 0)
        self.assertEqual(first["dataset"]["rows"], len(fixtures()[0]))
        self.assertAlmostEqual(
            first["summary"]["excess_return"],
            first["strategy"]["metrics"]["total_return"]
            - first["benchmark"]["metrics"]["total_return"],
        )
        exported = json.loads(json.dumps(load_experiment(first["id"])))
        rerun = run_experiment(rerun_payload(exported))
        self.assertEqual(first["id"], rerun["id"])
        self.assertEqual(first["summary"], rerun["summary"])
        self.assertEqual(first["strategy"], rerun["strategy"])
        self.assertNotIn("PRIVATE_TEST_KEY_123", json.dumps(exported))
        with self.assertRaises(ValueError):
            rerun_payload({**exported, "schema_version": 999})

    def test_uploaded_market_never_silently_receives_synthetic_weather(self):
        payload = {
            "market_csv": market_csv(),
            "strategy": preset("weather", slow=2),
            "provenance_note": "Self-generated test rows",
        }
        record = run_experiment(payload, persist=False)
        self.assertEqual(record["summary"]["trade_count"], 0)
        self.assertIn("User-imported", record["dataset"]["source"])
        self.assertFalse(any("Synthetic fixtures" in warning for warning in record["warnings"]))
        self.assertEqual(record["dataset"]["provenance_note"], "Self-generated test rows")
        event = {
            "observed_at": "2024-01-02T00:00:00Z",
            "available_at": "2024-01-02T12:00:00Z",
            "value": 1,
            "field": "temperature",
            "location": "Test town",
        }
        supplied = run_experiment({**payload, "events_csv": events_csv([event])}, persist=False)
        self.assertGreater(supplied["summary"]["trade_count"], 0)
        self.assertNotEqual(record["dataset"]["identity"], supplied["dataset"]["identity"])

    def test_ml_uses_user_execution_settings_for_strategy_and_benchmark(self):
        execution = {
            "initial_cash": 4321,
            "fee_bps": 23,
            "slippage_bps": 17,
            "periods_per_year": 252,
            "bar_seconds": 43200,
        }
        record = run_experiment(
            {"mode": "ml", "execution": execution, "ml": {"horizon": 2, "ridge_alphas": [1]}},
            persist=False,
        )
        self.assertEqual(record["strategy"]["config"], execution)
        self.assertEqual(record["benchmark"]["config"], execution)
        self.assertEqual(record["configuration"]["execution"], execution)
        self.assertEqual(record["strategy"]["equity"][0]["cash"], 4321)
        self.assertEqual(record["ml"]["search"]["trial_count"], 1)

    def test_feature_search_is_bounded_deterministic_and_returns_validation_only(self):
        first = feature_search({"trials": 3, "seed": 17})
        self.assertEqual(first, feature_search({"trials": 3, "seed": 17}))
        self.assertEqual(first["trial_count"], 3)
        self.assertEqual(len(first["trials"]), 3)
        for trial in first["trials"]:
            self.assertTrue(trial["features"])
            self.assertIn("mse", trial["validation"])
            self.assertNotIn("test", trial)
        for trials in (0, 11):
            with self.subTest(trials=trials), self.assertRaises(ValueError):
                feature_search({"trials": trials})

    def test_research_rejects_unknown_mode_settings_and_inconsistent_clock(self):
        for payload in (
            {"mode": "magic"},
            {"execution": {"secret_unsupported": 1}},
            {"execution": []},
            {"execution": {"bar_seconds": 3600}, "strategy": preset("buy_hold")},
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                run_experiment(payload, persist=False)


class ServerTests(IsolatedState):
    def setUp(self):
        super().setUp()
        self.server = make_server(0)
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        self.thread.start()
        self.port = self.server.server_port
        self.origin = f"http://127.0.0.1:{self.port}"
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.thread.join(timeout=3)
        self.server.server_close()

    def request(self, method, path, payload=None, headers=None, authenticated=True, raw=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        request_headers = {}
        body = raw
        if method == "POST":
            body = (
                json.dumps(payload if payload is not None else {}).encode() if raw is None else raw
            )
            request_headers.update({"Content-Type": "application/json", "Origin": self.origin})
        if authenticated:
            request_headers["X-Lab-Token"] = self.server.token
        request_headers.update(headers or {})
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            result = response.read()
            content_type = response.getheader("Content-Type", "")
            value = json.loads(result) if content_type.startswith("application/json") else result
            return response.status, value, dict(response.getheaders())
        finally:
            connection.close()

    def test_real_loopback_bootstrap_static_assets_and_security_headers(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        status, value, headers = self.request("GET", "/api/bootstrap", authenticated=False)
        self.assertEqual(status, 200)
        self.assertEqual(value["token"], self.server.token)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        for path in ("/", "/app.js", "/style.css"):
            with self.subTest(path=path):
                status, body, _ = self.request("GET", path)
                self.assertEqual(status, 200)
                self.assertTrue(body)

    def test_dns_rebinding_hosts_cross_origins_and_missing_tokens_are_rejected(self):
        for host in (
            "attacker.invalid",
            f"127.0.0.1.attacker.invalid:{self.port}",
            f"localhost.attacker.invalid:{self.port}",
            "127.0.0.1:1",
            "",
        ):
            with self.subTest(host=host):
                self.assertEqual(
                    self.request("GET", "/api/bootstrap", headers={"Host": host})[0], 403
                )
                self.assertEqual(
                    self.request("POST", "/api/shutdown", headers={"Host": host}, raw=b"")[0], 403
                )
        for origin in (
            "https://attacker.invalid",
            "null",
            "",
            f"https://127.0.0.1:{self.port}",
            "http://127.0.0.1:1",
        ):
            with self.subTest(origin=origin):
                self.assertEqual(
                    self.request(
                        "POST",
                        "/api/parse",
                        headers={"Origin": origin},
                        raw=b"",
                    )[0],
                    403,
                )
        self.assertEqual(self.request("POST", "/api/run", authenticated=False, raw=b"")[0], 403)
        self.assertEqual(
            self.request("POST", "/api/run", headers={"X-Lab-Token": "wrong"}, raw=b"")[0], 403
        )
        self.assertEqual(
            self.request("GET", "/api/experiments/" + "a" * 20, authenticated=False)[0], 403
        )

    def test_json_body_limits_and_invalid_shapes_fail_cleanly(self):
        for headers in (
            {"Content-Length": "3000001"},
            {"Content-Length": "0"},
            {"Content-Type": "text/plain"},
        ):
            with self.subTest(headers=headers):
                self.assertEqual(
                    self.request("POST", "/api/parse", headers=headers, raw=b"")[0], 413
                )
        self.assertEqual(self.request("POST", "/api/parse", raw=b"not-json")[0], 400)
        self.assertEqual(self.request("POST", "/api/parse", raw=b"[]")[0], 400)
        self.assertEqual(
            self.request("POST", "/api/parse", headers={"Content-Length": "invalid"})[0], 400
        )
        self.assertEqual(self.request("POST", "/api/missing")[0], 404)

    def test_parse_run_history_export_import_and_rerun(self):
        status, parsed, _ = self.request("POST", "/api/parse", {"text": "buy and hold bitcoin"})
        self.assertEqual(status, 200)
        status, record, _ = self.request(
            "POST", "/api/run", {"strategy": parsed, "name": "HTTP example"}
        )
        self.assertEqual(status, 200)
        status, history, _ = self.request("GET", "/api/history")
        self.assertEqual(status, 200)
        self.assertEqual(history[0]["id"], record["id"])
        status, exported, _ = self.request("GET", "/api/experiments/" + record["id"])
        self.assertEqual(status, 200)
        self.assertEqual(exported, record)
        status, imported, _ = self.request("POST", "/api/import", exported)
        self.assertEqual(status, 200)
        self.assertEqual(imported["id"], record["id"])
        status, rerun, _ = self.request("POST", "/api/rerun", {"id": record["id"]})
        self.assertEqual(status, 200)
        self.assertEqual(rerun["summary"], record["summary"])
        self.assertEqual(
            self.request("POST", "/api/import", {**exported, "schema_version": 999})[0], 400
        )
        self.assertEqual(self.request("GET", "/api/experiments/../credential")[0], 404)

    def test_settings_save_test_remove_and_provider_throttle_are_offline(self):
        key = "HTTP_TEST_KEY_123"
        self.assertEqual(
            self.request("POST", "/api/settings/save", {"key": key, "consent": False})[0], 400
        )
        status, saved, _ = self.request("POST", "/api/settings/save", {"key": key, "consent": True})
        self.assertEqual(status, 200)
        self.assertTrue(saved["saved"])
        with patch(
            "hypothesis_lab.server.alpha_vantage_test", return_value={"status": "connected"}
        ) as test:
            self.assertEqual(self.request("POST", "/api/settings/test")[0], 200)
            test.assert_called_once_with(key)
            self.assertEqual(self.request("POST", "/api/settings/test")[0], 400)
        with patch(
            "hypothesis_lab.server.kraken_snapshot",
            return_value={"kind": "completed_daily_snapshot"},
        ) as feed:
            self.assertEqual(self.request("POST", "/api/feed")[0], 200)
            self.assertEqual(self.request("POST", "/api/feed")[0], 400)
            feed.assert_called_once_with()
        status, removed, _ = self.request("POST", "/api/settings/remove")
        self.assertEqual(status, 200)
        self.assertFalse(removed["saved"])

    def test_provider_first_request_at_clock_zero_and_exact_cooldown_boundary(self):
        with (
            patch("hypothesis_lab.server.time.monotonic", return_value=0.0) as clock,
            patch(
                "hypothesis_lab.server.kraken_snapshot", return_value={"kind": "snapshot"}
            ) as feed,
            patch(
                "hypothesis_lab.server.alpha_vantage_test", return_value={"status": "connected"}
            ) as quote,
        ):
            status, body, _ = self.request("POST", "/api/feed")
            self.assertEqual(status, 200, body)
            self.assertEqual(feed.call_count, 1)
            clock.return_value = 59.999
            self.assertEqual(self.request("POST", "/api/feed")[0], 400)
            self.assertEqual(feed.call_count, 1)
            # Each provider has its own cooldown; the first request is always eligible.
            self.assertEqual(
                self.request("POST", "/api/settings/save", {"key": "TEST_KEY", "consent": True})[0],
                200,
            )
            self.assertEqual(self.request("POST", "/api/settings/test")[0], 200)
            self.assertEqual(quote.call_count, 1)
            clock.return_value = 60.0
            self.assertEqual(self.request("POST", "/api/feed")[0], 200)
            self.assertEqual(feed.call_count, 2)

    def test_concurrent_run_lock_and_shutdown(self):
        self.server.run_lock.acquire()
        try:
            self.assertEqual(self.request("POST", "/api/run")[0], 409)
        finally:
            self.server.run_lock.release()
        status, value, _ = self.request("POST", "/api/shutdown")
        self.assertEqual(status, 200)
        self.assertEqual(value["status"], "stopping")
        self.thread.join(timeout=3)
        self.assertFalse(self.thread.is_alive())


if __name__ == "__main__":
    unittest.main()
