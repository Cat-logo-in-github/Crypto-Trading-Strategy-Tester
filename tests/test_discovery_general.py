"""General catalog shapes and semantic distinctions, with synthetic offline responses."""

import json
import unittest
import urllib.parse
from unittest.mock import patch

from hypothesis_lab import sources
from hypothesis_lab.ideas import plan_idea


def encoded(value):
    return json.dumps(value).encode()


class GeneralDiscovery(unittest.TestCase):
    def test_nasa_returns_collection_reference_not_fake_pass_training_data(self):
        reply = {
            "feed": {
                "entry": [
                    {
                        "id": "C1234-CDDIS",
                        "title": "Satellite orbit measurements",
                        "summary": "Documented satellite orbit collection",
                        "time_start": "2000-01-01T00:00:00Z",
                        "platforms": ["SAT-1"],
                    }
                ]
            }
        }
        with patch.object(sources, "_download", return_value=encoded(reply)) as fetch:
            result = sources.search_sources(
                "satellite passes over New York vs New Jersey", "nasa", 5
            )
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(fetch.call_args.args[0]).query)
        self.assertEqual(query["keyword"], ["satellite orbit"])
        self.assertEqual(result["effective_queries"]["nasa"], "satellite orbit")
        collection = next(item for item in result["datasets"] if item["id"] == "C1234-CDDIS")
        self.assertFalse(collection["downloadable"])
        self.assertIsNone(collection["config"])
        self.assertEqual(collection["relevance"]["match"], "related")
        self.assertIn("not a numeric training series", " ".join(collection["limitations"]))
        with self.assertRaises(sources.SourceError):
            sources.fetch_source({"id": "nasa"})

    def test_european_multilingual_metadata_and_real_csv_resource_configuration(self):
        reply = {
            "success": True,
            "result": {
                "count": 10,
                "results": [
                    {
                        "id": "abc-123",
                        "translation": {
                            "en": {"title": "Traffic volume", "notes": "Measured vehicles"}
                        },
                        "publisher": {"name": "Transport agency"},
                        "resources": [
                            {"format": "CSV", "access_url": "[https://example.org/traffic.csv]"},
                            {"format": "HTML", "url": "https://example.org/landing"},
                        ],
                    }
                ],
            },
        }
        with patch.object(sources, "_download", return_value=encoded(reply)) as fetch:
            result = sources.search_sources("traffic volume", "europa", 2)
        self.assertEqual(urllib.parse.urlsplit(fetch.call_args.args[0]).hostname, "data.europa.eu")
        item = result["datasets"][0]
        self.assertEqual(item["title"], "Traffic volume")
        self.assertEqual(item["provider"], "Transport agency")
        self.assertEqual(
            item["config"],
            {
                "id": "custom_https",
                "url": "https://example.org/traffic.csv",
                "format": "csv",
                "auth": "none",
            },
        )
        self.assertTrue(item["downloadable"])
        self.assertEqual(item["relevance"]["match"], "exact")

    def test_hdx_private_request_only_and_binary_resources_do_not_become_download_buttons(self):
        items = [
            {"id": "private", "private": True, "title": "Private population"},
            {
                "id": "restricted",
                "title": "Population count",
                "is_requestdata_type": True,
                "resources": [{"format": "CSV", "url": "https://example.org/private.csv"}],
            },
            {
                "id": "binary",
                "title": "Population raster",
                "resources": [{"format": "GeoTIFF", "url": "https://example.org/pop.tif"}],
            },
            {
                "id": "unsafe",
                "title": "Population table",
                "resources": [
                    {"format": "JSON", "url": "https://127.0.0.1/private"},
                    {"format": "CSV", "url": "https://example.org/data?api_key=secret"},
                ],
            },
        ]
        with patch.object(
            sources,
            "_download",
            return_value=encoded({"success": True, "result": {"count": 4, "results": items}}),
        ):
            result = sources.search_sources("population", "hdx", 5)
        self.assertEqual(len(result["datasets"]), 3)
        self.assertFalse(any(item["downloadable"] for item in result["datasets"]))
        self.assertNotIn("secret", json.dumps(result))

    def test_auto_prioritizes_satellite_domain_ahead_of_shared_city_and_reports_partial_failure(
        self,
    ):
        def download(url, *args):
            if "cmr.earthdata" in url:
                return encoded(
                    {
                        "feed": {
                            "entry": [
                                {
                                    "id": "C123-NASA",
                                    "title": "Satellite orbit catalog",
                                    "summary": "Orbital observations",
                                }
                            ]
                        }
                    }
                )
            if "data.europa.eu" in url:
                raise sources.SourceError("Public catalog temporarily unavailable")
            return encoded(
                {
                    "results": [
                        {
                            "resource": {
                                "id": "abcd-1234",
                                "name": "New York New Jersey transport terminals",
                                "description": "Road inspections",
                            },
                            "metadata": {"domain": "data.example.org"},
                        }
                    ]
                }
            )

        with patch.object(sources, "_download", side_effect=download):
            result = sources.search_sources(
                "satellite passes over New York vs New Jersey", "auto", 10
            )
        self.assertEqual(set(result["catalogs_searched"]), {"nasa", "europa", "socrata"})
        transport = next(item for item in result["datasets"] if item["id"] == "abcd-1234")
        self.assertEqual(transport["relevance"]["match"], "weak")
        self.assertEqual(result["datasets"][-1]["id"], transport["id"])
        self.assertTrue(
            any("europa could not be searched" in warning for warning in result["warnings"])
        )
        ids = [item["id"] for item in result["datasets"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_malformed_new_catalog_envelopes_fail_with_source_errors(self):
        for catalog, reply in (
            ("nasa", {}),
            ("nasa", {"feed": {"entry": None}}),
            ("europa", {"success": False}),
            ("hdx", {"success": True, "result": {"results": None}}),
        ):
            with (
                self.subTest(catalog=catalog, reply=reply),
                patch.object(sources, "_download", return_value=encoded(reply)),
                self.assertRaises(sources.SourceError),
            ):
                sources.search_sources("population", catalog)

    def test_custom_tsv_ndjson_geojson_stay_local_bounded_and_remove_echoed_credentials(self):
        key = "USER_SESSION_ONLY_EXAMPLE_KEY"
        geo = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"count": 2, "api_key": key},
                    "geometry": {"type": "Point", "coordinates": [0, 1]},
                }
            ],
        }
        for format_name, raw in (
            ("tsv", f"count\tapi_key\n2\t{key}\n".encode()),
            ("ndjson", encoded({"count": 2, "api_key": key}) + b"\n"),
            ("geojson", encoded(geo)),
        ):
            with (
                self.subTest(format=format_name),
                patch.object(sources, "_download", return_value=raw),
            ):
                result = sources.fetch_source(
                    {
                        "id": "custom_https",
                        "url": "https://example.org/data",
                        "format": format_name,
                    },
                    key,
                )
            self.assertNotIn(key, json.dumps(result))
            self.assertNotIn("api_key", result["records"][0])
            self.assertEqual(result["provenance"]["input_format"], format_name)
        self.assertEqual(result["records"][0]["_latitude"], 1)

    def test_satellite_plan_names_missing_physical_definition_and_real_source_categories(self):
        plan = plan_idea("Buy when satellite passes over New York exceed New Jersey")
        self.assertEqual(plan["recommended_catalogs"][0], "nasa")
        self.assertEqual(plan["search_queries"][0]["match"], "related")
        self.assertEqual(plan["suggested_interpretation"]["aggregation"]["operation"], "count")
        self.assertTrue(any("Historical pass" in question for question in plan["clarifications"]))


if __name__ == "__main__":
    unittest.main()
