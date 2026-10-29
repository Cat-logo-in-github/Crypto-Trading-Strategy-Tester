"""Offline contracts for general discovery, local fetching and source integrity."""

import io
import json
import socket
import ssl
import unittest
import urllib.error
import urllib.parse
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from hypothesis_lab import sources


def encoded(value):
    return json.dumps(value).encode()


def wb_row(year="2020", value=1.5):
    return {"date": year, "value": value}


def port_row(day="2024-01-01", port="port0", **overrides):
    values = {
        "date": day,
        "portid": port,
        "portname": "Sample Port",
        "country": "Example",
        "ISO3": "EXP",
        "portcalls": 2,
        "import": 100,
        "export": 200,
    }
    values.update(overrides)
    return {"attributes": values}


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.cache = patch.object(sources, "_indicator_cache", (0.0, []))
        self.cache.start()
        self.addCleanup(self.cache.stop)

    def test_catalog_is_general_and_distinguishes_available_from_reference_sources(self):
        values = {item["id"]: item for item in sources.catalog()}
        self.assertTrue({"socrata", "worldbank", "custom_https", "portwatch"}.issubset(values))
        self.assertTrue(values["socrata"]["implemented"])
        self.assertFalse(values["aisstream"]["implemented"])
        self.assertIn("historical", values["aisstream"]["description"])
        json.dumps(values, allow_nan=False)

    def test_public_catalog_search_uses_real_response_schema_and_encoded_query(self):
        record = {
            "resource": {
                "id": "abcd-1234",
                "name": "Traffic volume",
                "description": "<p>Counts of vehicles.</p>",
                "columns_field_name": ["date", "vehicles"],
            },
            "metadata": {"domain": "data.example.org", "license": "Publisher Open License"},
        }
        with patch.object(
            sources, "_download", return_value=encoded({"results": [record], "resultSetSize": 42})
        ) as fetch:
            result = sources.search_sources("traffic & urban growth", "socrata", 3)
        parsed = urllib.parse.urlsplit(fetch.call_args.args[0])
        query = urllib.parse.parse_qs(parsed.query)
        self.assertEqual(parsed.hostname, "api.us.socrata.com")
        self.assertEqual(query["q"], ["traffic & urban growth"])
        self.assertEqual(query["only"], ["datasets"])
        dataset = result["datasets"][0]
        self.assertEqual(dataset["url"], "https://data.example.org/resource/abcd-1234.json")
        self.assertEqual(dataset["license"], "Publisher Open License")
        self.assertEqual(dataset["columns"], ["date", "vehicles"])
        self.assertNotIn("<p>", dataset["description"])
        self.assertEqual(result["total_matches"], 42)
        self.assertTrue(
            any(
                "proxy" in message.lower() or "proxies" in message.lower()
                for message in result["warnings"]
            )
        )

    def test_catalog_rejects_forged_resource_ids_domains_and_malformed_envelopes(self):
        bad = {
            "resource": {"id": "abcd-1234", "name": "Fake"},
            "metadata": {"domain": "public.example@127.0.0.1"},
        }
        with patch.object(sources, "_download", return_value=encoded({"results": [bad]})):
            self.assertEqual(sources.search_sources("traffic")["datasets"], [])
        for value in ([], {"results": "not a record array"}, {"error": "changed schema"}):
            with (
                self.subTest(value=value),
                patch.object(sources, "_download", return_value=encoded(value)),
                self.assertRaises(sources.SourceError),
            ):
                sources.search_sources("traffic")
        for value in (None, "not an object", {"resource": None, "metadata": {}}):
            with (
                self.subTest(row=value),
                patch.object(sources, "_download", return_value=encoded({"results": [value]})),
            ):
                try:
                    result = sources.search_sources("traffic")
                except sources.SourceError:
                    continue
                self.assertEqual(result["datasets"], [])

    def test_query_and_limit_validation_are_bounded_and_sanitized(self):
        for value in ("", "x", "x" * 201, None, 7):
            with self.subTest(query=value), self.assertRaises(sources.SourceError):
                sources.search_sources(value)
        for value in (0, 21, True, 1.5, "invalid", None):
            with self.subTest(limit=value), self.assertRaises(sources.SourceError):
                sources.search_sources("traffic", limit=value)
        with self.assertRaises(sources.SourceError):
            sources.search_sources("traffic", "invented repository")

    def test_worldbank_indicator_search_is_ranked_bounded_and_memory_cached(self):
        records = [
            {
                "id": "SP.URB.GROW",
                "name": "Urban population growth",
                "sourceNote": "Annual percentage",
                "sourceOrganization": "World Bank",
            },
            {"id": "NY.GDP.MKTP.CD", "name": "GDP", "sourceNote": "Gross domestic product"},
        ]
        with patch.object(
            sources, "_download", return_value=encoded([{"pages": 1}, records])
        ) as fetch:
            first = sources.search_sources("urban growth", "worldbank", 2)
            second = sources.search_sources("GDP", "worldbank", 2)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(first["datasets"][0]["config"]["indicator"], "SP.URB.GROW")
        self.assertEqual(second["datasets"][0]["id"], "NY.GDP.MKTP.CD")
        self.assertFalse(first["datasets"][0]["key_required"])
        self.assertIn("terms", first["datasets"][0]["license"])
        self.assertIn("source=2", fetch.call_args.args[0])

    def test_worldbank_search_pagination_budget_and_bad_metadata(self):
        replies = [
            encoded([{"pages": 999}, [{"id": f"X.URB.{i}", "name": "Urban growth"}]])
            for i in range(3)
        ]
        with patch.object(sources, "_download", side_effect=replies) as fetch:
            result = sources.search_sources("urban", "worldbank", 2)
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(len(result["datasets"]), 2)
        sources._indicator_cache = (0.0, [])
        for value in ([{"pages": "not numeric"}, []], [{"pages": 1}, [None]], {"error": "down"}):
            with (
                self.subTest(value=value),
                patch.object(sources, "_download", return_value=encoded(value)),
            ):
                try:
                    result = sources.search_sources("urban", "worldbank", 2)
                except sources.SourceError:
                    continue
                self.assertEqual(result["datasets"], [])


class FetchTests(unittest.TestCase):
    def test_worldbank_annual_values_are_not_silently_backdated(self):
        payload = [{"pages": 1}, [wb_row("2022", 2.5), wb_row("2021", None), wb_row("2020", 1.5)]]
        with patch.object(sources, "_download", return_value=encoded(payload)) as fetch:
            result = sources.fetch_source(
                {
                    "id": "worldbank",
                    "country": "USA",
                    "indicator": "SP.URB.GROW",
                    "start": "2020",
                    "end": "2022",
                }
            )
        self.assertEqual([row["year"] for row in result["records"]], [2020, 2022])
        row = result["records"][0]
        self.assertEqual(row["observed_at"], "2021-01-01T00:00:00+00:00")
        self.assertGreater(
            datetime.fromisoformat(row["available_at"]), datetime(2023, 1, 1, tzinfo=UTC)
        )
        self.assertFalse(result["provenance"]["point_in_time"])
        self.assertEqual(result["mapping_suggestion"]["availability_mode"], "column")
        self.assertNotIn("?", result["provenance"]["url"])
        self.assertEqual(
            urllib.parse.parse_qs(urllib.parse.urlsplit(fetch.call_args.args[0]).query)["date"],
            ["2020:2022"],
        )

    def test_worldbank_rejects_invalid_and_inconsistent_provider_observations(self):
        config = {
            "id": "worldbank",
            "country": "USA",
            "indicator": "SP.URB.GROW",
            "start": 2020,
            "end": 2022,
        }
        bad_sets = [
            [None],
            [wb_row("2020", True)],
            [wb_row("2020", float("nan"))],
            [wb_row("1800", 1)],
            [wb_row("2020", 1), wb_row("2020", 2)],
            [wb_row("2023", 1)],
        ]
        for rows in bad_sets:
            with (
                self.subTest(rows=rows),
                patch.object(sources, "_download", return_value=encoded([{"pages": 1}, rows])),
                self.assertRaises(sources.SourceError),
            ):
                sources.fetch_source(config)
        for change in (
            {"country": "USA;all"},
            {"indicator": "X?bad"},
            {"start": "nonsense"},
            {"start": True},
            {"start": 2022.5},
            {"start": 1950},
        ):
            with self.subTest(change=change), self.assertRaises(sources.SourceError):
                sources.fetch_source({**config, **change})

    def test_socrata_download_uses_publisher_and_separate_optional_app_token(self):
        key = "private-test-value-for-session"
        with patch.object(
            sources,
            "_download",
            return_value=encoded(
                [{"observed": "2024-01-01", "traffic": 27, "api_key": key, "note": f"echo:{key}"}]
            ),
        ) as fetch:
            result = sources.fetch_source(
                {
                    "id": "socrata",
                    "domain": "data.example.org",
                    "dataset_id": "abcd-1234",
                    "limit": 15,
                    "where": "traffic > 10",
                },
                key,
            )
        url, headers = fetch.call_args.args
        self.assertEqual(headers, {"X-App-Token": key})
        self.assertNotIn(key, url)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        self.assertEqual(query["$limit"], ["15"])
        self.assertEqual(query["$where"], ["traffic > 10"])
        self.assertNotIn(key, json.dumps(result))
        self.assertEqual(result["records"][0]["traffic"], 27)
        self.assertNotIn("api_key", result["records"][0])
        self.assertNotIn("?", result["provenance"]["url"])
        self.assertTrue(any("at most 15" in value for value in result["warnings"]))

    def test_socrata_download_limits_and_domains_are_validated_before_network(self):
        good = {"id": "socrata", "domain": "data.example.org", "dataset_id": "abcd-1234"}
        changes = [
            {"domain": "a.example@127.0.0.1"},
            {"dataset_id": "../bad"},
            {"limit": 0},
            {"limit": 5001},
            {"limit": "invalid"},
            {"limit": True},
            {"limit": 2.5},
            {"where": "x" * 1001},
        ]
        for change in changes:
            with (
                self.subTest(change=change),
                patch.object(sources, "_download") as fetch,
                self.assertRaises(sources.SourceError),
            ):
                sources.fetch_source({**good, **change})
            fetch.assert_not_called()

    def test_custom_json_paths_credentials_and_query_provenance(self):
        key = "session-key-value"
        payload = {
            "data": {
                "items": [
                    {
                        "attributes": {
                            "time": "2024-01-01",
                            "sales": 3,
                            "nested": {"password": key, "ok": 2},
                        }
                    }
                ]
            }
        }
        with patch.object(sources, "_download", return_value=encoded(payload)) as fetch:
            result = sources.fetch_source(
                {
                    "id": "custom_https",
                    "url": "https://data.example.org/dataset?region=private-region",
                    "format": "json",
                    "records_path": "data.items",
                    "record_path": "attributes",
                    "auth": "bearer",
                },
                key,
            )
        self.assertEqual(fetch.call_args.args[1], {"Authorization": "Bearer " + key})
        self.assertEqual(result["records"][0]["sales"], 3)
        self.assertEqual(result["records"][0]["nested"], {"ok": 2})
        self.assertEqual(result["provenance"]["url"], "https://data.example.org/dataset")
        self.assertNotIn(key, json.dumps(result))
        self.assertNotIn("private-region", json.dumps(result))
        self.assertEqual(json.loads(result["content"]), result["records"])

    def test_custom_csv_preserves_rows_and_discards_credential_columns(self):
        body = b"date,temperature,traffic,api_key\n2024-01-01,5,20,key-value\n2024-01-02,7,25,key-value\n"
        with patch.object(sources, "_download", return_value=body):
            result = sources.fetch_source(
                {"id": "http", "url": "https://data.example.org/data.csv", "format": "csv"}
            )
        self.assertEqual(result["columns"], ["date", "temperature", "traffic"])
        self.assertEqual(result["records"][1]["traffic"], "25")
        self.assertNotIn("key-value", result["content"])
        for body in (b"a,a\n1,2\n", b"a\n1,2\n", b"a\n", b"\xff"):
            with (
                self.subTest(body=body),
                patch.object(sources, "_download", return_value=body),
                self.assertRaises(sources.SourceError),
            ):
                sources.fetch_source(
                    {
                        "id": "custom_https",
                        "url": "https://data.example.org/data.csv",
                        "format": "csv",
                    }
                )

    def test_custom_missing_or_invalid_authentication_never_sends_a_request(self):
        good = {"id": "custom_https", "url": "https://data.example.org/data", "auth": "api_key"}
        pairs = [
            ({}, None),
            ({}, "line\nbreak"),
            ({"header_name": "Host"}, "session-value"),
            ({"header_name": "Cookie"}, "session-value"),
            ({"header_name": "Sec-Fetch-Site"}, "session-value"),
            ({"auth": "invented"}, "session-value"),
        ]
        for change, key in pairs:
            with (
                self.subTest(change=change),
                patch.object(sources, "_download") as fetch,
                self.assertRaises(sources.SourceError) as caught,
            ):
                sources.fetch_source({**good, **change}, key)
            fetch.assert_not_called()
            if key:
                self.assertNotIn(key, str(caught.exception))

    def test_json_and_record_budget_are_bounded(self):
        for body in (
            b"not json",
            b"[NaN]",
            b"[Infinity]",
            b"\xff",
            encoded([]),
            encoded([3]),
            encoded([{"a": 1}] * 5001),
            encoded([{str(i): i for i in range(101)}]),
        ):
            with (
                self.subTest(prefix=body[:20]),
                patch.object(sources, "_download", return_value=body),
                self.assertRaises(sources.SourceError),
            ):
                sources.fetch_source(
                    {"id": "custom_https", "url": "https://data.example.org/data", "format": "json"}
                )
        for path in ("data[0]", "a." * 10, "__import__('os')"):
            with (
                self.subTest(path=path),
                patch.object(sources, "_download", return_value=encoded({"a": []})),
                self.assertRaises(sources.SourceError),
            ):
                sources.fetch_source(
                    {
                        "id": "custom_https",
                        "url": "https://data.example.org/data",
                        "records_path": path,
                    }
                )

    def test_portwatch_day_completion_pagination_and_acquisition_time(self):
        first = datetime(2019, 1, 1, tzinfo=UTC)
        rows = [port_row((first + timedelta(days=i)).date().isoformat()) for i in range(1001)]
        responses = [
            encoded({"features": rows[:1000], "exceededTransferLimit": True}),
            encoded({"features": rows[1000:]}),
        ]
        with patch.object(sources, "_download", side_effect=responses) as fetch:
            result = sources.fetch_source(
                {"id": "portwatch", "port_id": "PORT0", "start": "2019-01-01", "end": "2022-01-01"}
            )
        self.assertEqual(len(result["records"]), 1001)
        self.assertEqual(result["records"][0]["observed_at"], "2019-01-02T00:00:00+00:00")
        self.assertGreater(
            datetime.fromisoformat(result["records"][0]["available_at"]),
            datetime(2022, 1, 1, tzinfo=UTC),
        )
        self.assertFalse(result["provenance"]["point_in_time"])
        self.assertIn("acquisition", " ".join(result["warnings"]))
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(fetch.call_args_list[1].args[0]).query)
        self.assertEqual(query["resultOffset"], ["1000"])
        self.assertIn("portid = 'port0'", query["where"][0])

    def test_portwatch_invalid_filters_and_malformed_provider_rows_fail(self):
        good = {"id": "portwatch", "port_id": "port0", "start": "2024-01-01", "end": "2024-01-02"}
        for change in (
            {"port_id": "port0' OR 1=1"},
            {"start": "2018-01-01"},
            {"end": "2023-01-01"},
            {"start": "not-date"},
        ):
            with self.subTest(change=change), self.assertRaises(sources.SourceError):
                sources.fetch_source({**good, **change})
        for payload in (
            {"error": {"message": "private response"}},
            {"features": []},
            {"features": [port_row(port="port1")]},
            {"features": [port_row(portcalls=-1)]},
            {"features": [port_row(), port_row()]},
            {"features": [None]},
        ):
            with (
                self.subTest(payload=payload),
                patch.object(sources, "_download", return_value=encoded(payload)),
                self.assertRaises(sources.SourceError),
            ):
                sources.fetch_source(good)
        with self.assertRaises(sources.SourceError):
            sources.fetch_source({"id": "aisstream"}, "private-session-key")


class TransportTests(unittest.TestCase):
    def test_url_contract_rejects_nonpublic_embedded_secret_or_nontls_requests(self):
        for url in (
            "http://data.example.org/a",
            "file:///private",
            "https://127.0.0.1/a",
            "https://[::1]/a",
            "https://10.0.0.1/a",
            "https://localhost/a",
            "https://data.local/a",
            "https://user:password@data.example.org/a",
            "https://data.example.org:8443/a",
            "https://data.example.org/a?api_key=private",
            "https://data.example.org/a?access_token=private",
            "https://data.example.org/a#fragment",
            "https://data.example.org/a\n",
        ):
            with self.subTest(url=url), self.assertRaises(sources.SourceError):
                sources._url(url)
        self.assertEqual(
            sources._url("https://data.example.org/a?region=one")[1], "https://data.example.org/a"
        )

    def test_dns_rejects_mixed_private_answers_and_pins_public_connection(self):
        def answer(address):
            return (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))

        for values in ([], [answer("127.0.0.1")], [answer("93.184.216.34"), answer("10.0.0.1")]):
            with (
                self.subTest(values=values),
                patch.object(socket, "getaddrinfo", return_value=values),
                self.assertRaises(sources.SourceError),
            ):
                sources._public_addresses("data.example.org", 443)
        with patch.object(
            socket, "getaddrinfo", return_value=[answer("93.184.216.34"), answer("93.184.216.34")]
        ):
            self.assertEqual(sources._public_addresses("data.example.org", 443), ["93.184.216.34"])
        connection = sources._PinnedHTTPSConnection(
            "data.example.org", context=ssl.create_default_context(), timeout=15
        )
        context, raw_socket, tls_socket = MagicMock(), MagicMock(), MagicMock()
        context.wrap_socket.return_value = tls_socket
        connection._context = context
        with (
            patch.object(sources, "_public_addresses", return_value=["93.184.216.34"]),
            patch.object(socket, "create_connection", return_value=raw_socket) as connect,
        ):
            connection.connect()
        connect.assert_called_once_with(("93.184.216.34", 443), timeout=15)
        context.wrap_socket.assert_called_once_with(raw_socket, server_hostname="data.example.org")
        self.assertIs(connection.sock, tls_socket)

    def test_download_never_forwards_redirected_keys_and_sanitizes_provider_errors(self):
        with self.assertRaises(sources.SourceError) as caught:
            sources._NoRedirect().redirect_request(
                None, None, 302, "redirect", {}, "https://attacker.example/?key=private"
            )
        self.assertNotIn("attacker.example", str(caught.exception))
        secret = "secret-session-value"
        for error in (
            urllib.error.HTTPError(
                "https://provider.example/" + secret, 401, secret, {}, io.BytesIO(secret.encode())
            ),
            urllib.error.HTTPError("https://provider.example", 429, secret, {}, None),
            urllib.error.URLError(secret),
        ):
            opener = MagicMock()
            opener.open.side_effect = error
            with (
                self.subTest(error=type(error).__name__),
                patch.object(sources.urllib.request, "build_opener", return_value=opener),
                self.assertRaises(sources.SourceError) as caught,
            ):
                sources._download("https://provider.example/data", {"X-API-Key": secret})
            self.assertNotIn(secret, str(caught.exception))

    def test_download_has_size_timeout_and_no_proxy_policy(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b"x" * (sources.MAX_BYTES + 1)
        opener = MagicMock()
        opener.open.return_value = response
        with (
            patch.object(sources.urllib.request, "build_opener", return_value=opener) as build,
            self.assertRaises(sources.SourceError),
        ):
            sources._download("https://data.example.org/data")
        response.read.assert_called_once_with(sources.MAX_BYTES + 1)
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 15)
        handlers = build.call_args.args
        self.assertEqual(handlers[0].proxies, {})
        self.assertIsInstance(handlers[1], sources._NoRedirect)
        self.assertIsInstance(handlers[2], sources._PinnedHTTPSHandler)


if __name__ == "__main__":
    unittest.main()
