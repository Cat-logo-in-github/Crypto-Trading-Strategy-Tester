"""Local, bounded public-data connectors and user-selected HTTPS tabular sources.

Credentials are function arguments only: this module has no disk persistence,
telemetry or application-operator endpoint. Public indicator metadata has a
bounded in-memory cache. Redirects never receive credentials.
"""

from __future__ import annotations

import csv
import http.client
import io
import ipaddress
import json
import math
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from typing import Any

PORTWATCH_LAYER = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Ports_Data/FeatureServer/0"
PORTWATCH_REFERENCE = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/PortWatch_ports_database/FeatureServer/0"
MAX_BYTES = 4_000_000
MAX_ROWS = 5000
PORTWATCH_FIELDS = (
    "date",
    "portid",
    "portname",
    "country",
    "ISO3",
    "portcalls",
    "import",
    "export",
)
SECRET_FIELDS = {
    "apikey",
    "api_key",
    "api-key",
    "token",
    "access_token",
    "secret",
    "password",
    "authorization",
    "credential",
}


class SourceError(ValueError):
    """Sanitized, user-actionable source failure without response bodies or secrets."""


def _source_int(value: Any, label: str, minimum: int, maximum: int) -> int:
    """Normalize an integer form value without truncating or echoing its contents."""
    if isinstance(value, bool):
        raise SourceError(f"{label} must be an integer from {minimum} to {maximum}")
    try:
        number = float(value)
        if not math.isfinite(number) or not number.is_integer() or not minimum <= number <= maximum:
            raise ValueError("Out of range")
    except (ValueError, TypeError, OverflowError):
        raise SourceError(f"{label} must be an integer from {minimum} to {maximum}") from None
    return int(number)


def catalog() -> list[dict[str, Any]]:
    return [
        {
            "id": "auto",
            "name": "Search across relevant public catalogs",
            "description": "Search several real catalogs and rank measured concepts ahead of geographic coincidences. Metadata matches do not prove that data is usable.",
            "authentication": "none for public discovery",
            "implemented": True,
            "capabilities": ["search"],
            "documentation": "docs/data-sources.html",
            "limits": "At most three catalogs per search; failures and partial results are reported.",
        },
        {
            "id": "nasa",
            "name": "NASA Earthdata collections",
            "description": "Discover Earth observation, satellite, climate and geodesy collections in NASA CMR. These are collection metadata, not ready-made pass events or imagery-derived training features.",
            "authentication": "public metadata; collection downloads may require your Earthdata account",
            "implemented": True,
            "capabilities": ["search"],
            "documentation": "https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html",
            "limits": "Collection discovery only. HDF/NetCDF/raster extraction and orbital propagation require an external documented conversion.",
        },
        {
            "id": "europa",
            "name": "European open data catalog",
            "description": "Discover public datasets from European institutions and national/regional catalogs across many domains.",
            "authentication": "none for discovery; resource-specific access",
            "implemented": True,
            "capabilities": ["search"],
            "documentation": "https://data.europa.eu/api/hub/search/",
            "limits": "Download supported public HTTPS CSV/TSV/JSON/NDJSON/GeoJSON resources only. Publisher terms, actual file size and availability apply.",
        },
        {
            "id": "hdx",
            "name": "UN OCHA Humanitarian Data Exchange",
            "description": "Discover global population, infrastructure, environment, health and humanitarian datasets. Restricted/request-only and large binary resources remain references.",
            "authentication": "public metadata; resource-specific access",
            "implemented": True,
            "capabilities": ["search"],
            "documentation": "https://data.humdata.org/faq",
            "limits": "Public catalog metadata; each resource has its own access, license, sensitivity and format requirements.",
        },
        {
            "id": "socrata",
            "name": "Public data catalog search",
            "description": "Search across public city, government and nonprofit catalogs: traffic, permits, business activity, environment and more.",
            "authentication": "none for discovery; source-dependent for downloads",
            "implemented": True,
            "documentation": "https://dev.socrata.com/data/",
            "limits": "Search metadata first. Each publisher sets its own terms, quotas and dataset coverage.",
        },
        {
            "id": "worldbank",
            "name": "World Bank indicators",
            "description": "Search development indicators covering cities, population, climate, transport, trade and the economy.",
            "authentication": "none",
            "implemented": True,
            "documentation": "https://datahelpdesk.worldbank.org/knowledgebase/articles/889392",
            "default_config": {
                "id": "worldbank",
                "indicator": "SP.URB.GROW",
                "country": "USA",
                "start": "2000",
                "end": "2024",
            },
            "limits": "Mostly annual, revised indicators. This is not a point-in-time publication archive; inspect source-specific licensing.",
        },
        {
            "id": "portwatch",
            "name": "IMF PortWatch - daily maritime activity",
            "description": "Public AIS-derived daily port calls and estimated import/export tonnes. Revised historical aggregates, not a live vessel feed or historical publication archive.",
            "authentication": "none",
            "implemented": True,
            "documentation": "https://portwatch.imf.org/",
            "terms": "https://www.imf.org/external/terms.htm",
            "reference": PORTWATCH_REFERENCE,
            "default_config": {
                "id": "portwatch",
                "port_id": "port0",
                "start": "2024-01-01",
                "end": "2024-06-01",
            },
            "limits": "One port, 2019 onward, up to 5,000 daily rows and five API pages; no key. Source availability and IMF terms apply.",
        },
        {
            "id": "custom_https",
            "name": "Your HTTPS table / JSON API",
            "description": "Fetch a public HTTPS dataset directly from your computer. Supports CSV, TSV, JSON, NDJSON and GeoJSON properties/points, with an optional separate provider key.",
            "authentication": "optional user key",
            "implemented": True,
            "documentation": "docs/data-sources.html",
            "default_config": {
                "id": "custom_https",
                "url": "",
                "format": "json",
                "records_path": "",
                "auth": "none",
                "header_name": "X-API-Key",
            },
            "limits": "GET only, public HTTPS addresses, no redirects/proxies, 4 MB, 5,000 rows; no automatic multi-page crawling.",
        },
        {
            "id": "aisstream",
            "name": "AISStream - live vessel messages (reference)",
            "description": "Free account API key and a backend WebSocket subscription are required. It has no durable historical replay. This is a reference, not an implemented training-data fetcher; use a historical provider or exported observations for training.",
            "authentication": "user key required",
            "implemented": False,
            "documentation": "https://aisstream.io/documentation",
            "account": "https://aisstream.io/",
            "limits": "Live-only WebSocket; no SLA. The current app does not collect this stream.",
        },
    ]


def _public_addresses(host: str, port: int) -> list[str]:
    """Resolve once, reject every private answer, and return addresses to pin."""
    try:
        answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        addresses = list(dict.fromkeys(str(answer[4][0]) for answer in answers))
        if not addresses or any(not ipaddress.ip_address(value).is_global for value in addresses):
            raise SourceError("Data sources must resolve only to public internet addresses")
        return addresses
    except (socket.gaierror, ValueError):
        raise SourceError(
            "The source hostname could not be resolved to a public internet address"
        ) from None


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    _context: ssl.SSLContext

    def connect(self) -> None:
        addresses = _public_addresses(self.host, self.port)
        # Pin the validated address, while TLS verifies the original hostname.
        # urllib's proxy support is disabled, so no CONNECT tunnel is involved.
        last_error: OSError | None = None
        for address in addresses:
            try:
                connection = socket.create_connection((address, self.port), timeout=self.timeout)
                try:
                    self.sock = self._context.wrap_socket(connection, server_hostname=self.host)
                except Exception:
                    connection.close()
                    raise
                return
            except OSError as error:
                last_error = error
        if last_error is not None:
            raise last_error


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    _context: ssl.SSLContext

    def https_open(self, request):
        return self.do_open(_PinnedHTTPSConnection, request, context=self._context)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        raise SourceError(
            "The provider redirected this request. Enter its final documented HTTPS URL; credentials were not forwarded."
        )


def _url(value: Any) -> tuple[str, str]:
    if not isinstance(value, str) or not value or len(value) > 4000:
        raise SourceError("Enter a provider HTTPS URL of at most 4,000 characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise SourceError("Source URLs must not contain control characters")
    try:
        parsed = urllib.parse.urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ValueError("Invalid source URL")
        if parsed.port not in {None, 443}:
            raise ValueError("Unsupported port")
        host = parsed.hostname
        if host.lower() in {"localhost", "localhost.localdomain"} or host.lower().endswith(
            (".local", ".localhost", ".internal")
        ):
            raise ValueError("Local address")
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
        if literal is not None and not literal.is_global:
            raise ValueError("Nonpublic address")
        for key, _ in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
            compact = key.lower().replace("-", "_")
            if compact in SECRET_FIELDS or any(
                word in compact
                for word in ("password", "secret", "apikey", "api_key", "access_token", "signature")
            ):
                raise SourceError(
                    "Keep API keys out of URLs. Use the separate session key field and header authentication."
                )
    except SourceError:
        raise
    except ValueError:
        raise SourceError(
            "Use a public HTTPS URL on port 443, without embedded credentials or fragments"
        ) from None
    # Queries can contain personal parameters, so provenance retains host/path only.
    return value, urllib.parse.urlunsplit(("https", parsed.netloc, parsed.path or "/", "", ""))


def _download(url: str, headers: dict[str, str] | None = None) -> bytes:
    _url(url)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "HypothesisLab/0.3 local-data-research",
            "Accept": "application/json,text/csv",
            **(headers or {}),
        },
    )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _NoRedirect(), _PinnedHTTPSHandler()
    )
    try:
        with opener.open(request, timeout=15) as response:
            body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise SourceError(
                "Provider response exceeds 4 MB; narrow the query or import a smaller file"
            )
        return body
    except SourceError:
        raise
    except urllib.error.HTTPError as error:
        if error.code in {401, 403}:
            raise SourceError(
                "Provider access was denied. Enter your own valid key or check the provider entitlement and terms."
            ) from None
        if error.code == 429:
            raise SourceError(
                "Provider quota is exhausted. Wait or adjust the provider plan before retrying."
            ) from None
        raise SourceError(
            f"Provider returned HTTP {error.code}; check its status and query settings"
        ) from None
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        raise SourceError(
            "The provider could not be reached securely. Check your network and source settings; no credentials were logged."
        ) from None


def _json(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8-sig"), parse_constant=lambda value: _nonfinite())
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError):
        raise SourceError("The provider did not return valid finite UTF-8 JSON") from None


def _nonfinite():
    raise ValueError("Nonfinite JSON constant")


def _records(value: Any, path: str = "", record_path: str = "") -> list[dict[str, Any]]:
    for component in _path(path):
        if not isinstance(value, dict) or component not in value:
            raise SourceError(
                "The JSON record-array path was not found; inspect the provider schema"
            )
        value = value[component]
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_ROWS:
        raise SourceError("Choose a nonempty JSON record array with at most 5,000 rows")
    records = []
    for item in value:
        for component in _path(record_path):
            if not isinstance(item, dict) or component not in item:
                raise SourceError("The JSON record-object path was not found")
            item = item[component]
        if not isinstance(item, dict) or not item or len(item) > 100:
            raise SourceError("Each row must be an object with 1..100 named fields")
        records.append(item)
    return records


def _path(value: str) -> list[str]:
    if not isinstance(value, str) or len(value) > 200:
        raise SourceError("JSON paths must be short dot-separated object field names")
    parts = value.split(".") if value else []
    if len(parts) > 8 or any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", part) for part in parts):
        raise SourceError("JSON paths support at most eight dot-separated object fields")
    return parts


def _clean_records(records: list[dict[str, Any]], credential: str | None) -> list[dict[str, Any]]:
    def clean(value):
        if isinstance(value, dict):
            return {
                str(key): clean(item)
                for key, item in value.items()
                if str(key).lower() not in SECRET_FIELDS
            }
        if isinstance(value, list):
            return [clean(item) for item in value]
        if isinstance(value, str) and credential:
            if value == credential:
                return "[redacted]"
            if len(credential) >= 8:
                return value.replace(credential, "[redacted]")
        return value

    return [clean(row) for row in records]


def _custom(config: dict, credential: str | None) -> dict:
    url, public_url = _url(config.get("url"))
    auth = config.get("auth", "none")
    headers: dict[str, str] = {}
    if auth not in {"none", "bearer", "api_key"}:
        raise SourceError("Authentication must be none, bearer or api_key")
    if auth != "none":
        if not isinstance(credential, str) or not credential:
            raise SourceError(
                "This source requires your own API key. Enter it in the session key field."
            )
        if len(credential) > 2048 or any(ord(char) < 32 or ord(char) > 126 for char in credential):
            raise SourceError("The provider key must be printable text without line breaks")
        if auth == "bearer":
            headers["Authorization"] = "Bearer " + credential
        else:
            name = config.get("header_name", "X-API-Key")
            denied = {
                "host",
                "origin",
                "cookie",
                "referer",
                "content-length",
                "connection",
                "proxy-authorization",
                "transfer-encoding",
                "te",
                "user-agent",
            }
            if (
                not isinstance(name, str)
                or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", name)
                or name.lower() in denied
                or name.lower().startswith("sec-")
            ):
                raise SourceError("Choose the provider's API-key header, such as X-API-Key")
            headers[name] = credential
    raw = _download(url, headers)
    format_name = config.get("format", "json")
    if format_name == "json":
        records = _records(
            _json(raw), config.get("records_path", ""), config.get("record_path", "")
        )
    elif format_name in {"csv", "tsv"}:
        try:
            csv.field_size_limit(MAX_BYTES)
            rows = csv.DictReader(
                io.StringIO(raw.decode("utf-8-sig")),
                delimiter="\t" if format_name == "tsv" else ",",
            )
            if (
                not rows.fieldnames
                or len(rows.fieldnames) > 100
                or any(not name.strip() for name in rows.fieldnames)
                or len(rows.fieldnames) != len(set(rows.fieldnames))
            ):
                raise SourceError("CSV requires 1..100 distinct column names")
            records = []
            for row in rows:
                if None in row:
                    raise SourceError("CSV rows contain more cells than the header")
                records.append(dict(row))
                if len(records) > MAX_ROWS:
                    raise SourceError("Source has more than 5,000 rows; narrow its query")
            if not records:
                raise SourceError("The CSV source contains no observations")
        except (UnicodeError, csv.Error):
            raise SourceError("The provider did not return a valid UTF-8 CSV table") from None
    elif format_name in {"ndjson", "geojson"}:
        from .features import read_records

        try:
            records = read_records(raw.decode("utf-8-sig"), format_name)
            if len(records) > MAX_ROWS:
                raise SourceError("Source has more than 5,000 rows; narrow its query")
        except (UnicodeError, ValueError, RecursionError):
            raise SourceError(
                "Source did not return a supported bounded UTF-8 table in the chosen format"
            ) from None
        # The local tabular normalization is explicit; raster/polygon geometry is not invented.
        format_name = "json"
    else:
        raise SourceError("Select csv, tsv, json, ndjson or geojson as the source format")
    records = _clean_records(records, credential)
    columns = list(dict.fromkeys(key for row in records for key in row))
    if not columns:
        raise SourceError("No noncredential data columns were returned")
    if format_name in {"csv", "tsv"}:
        output = io.StringIO()
        writer = csv.DictWriter(
            output, fieldnames=columns, delimiter="\t" if format_name == "tsv" else ","
        )
        writer.writeheader()
        writer.writerows(records)
        content = output.getvalue()
    else:
        content = json.dumps(records, allow_nan=False, separators=(",", ":"))
    acquired = datetime.now(UTC).isoformat()
    return {
        "source": "custom_https",
        "name": "User-selected HTTPS data",
        "format": format_name,
        "content": content,
        "records": records,
        "columns": columns,
        "provenance": {
            "provider": urllib.parse.urlsplit(public_url).hostname,
            "url": public_url,
            "fetched_at": acquired,
            "authentication": auth,
            "input_format": config.get("format", "json"),
            "storage": "session only; no operator transmission",
        },
        "mapping_suggestion": {"availability_mode": "acquired", "acquired_at": acquired},
        "warnings": [
            "Downloaded directly by the local app. Source credentials and URL queries are omitted from provenance; no app-operator server receives them.",
            "Select observation and availability columns explicitly. If historical publication times are absent, use acquisition time or an explicitly labeled assumed lag; do not silently backdate revised data.",
            "This generic connector performs one bounded GET. Provider access, licensing, entitlements, pagination and data quality remain source-specific.",
        ],
    }


def _portwatch(config: dict) -> dict:
    port = config.get("port_id", "")
    if not isinstance(port, str) or not re.fullmatch(r"port\d{1,6}", port, re.IGNORECASE):
        raise SourceError(
            "Choose a PortWatch port ID, such as port0 (Abbot Point); see the port reference catalogue"
        )
    port = port.lower()
    try:
        first, last = (
            date.fromisoformat(config.get("start", "")),
            date.fromisoformat(config.get("end", "")),
        )
    except (ValueError, TypeError):
        raise SourceError("Choose start and end dates in YYYY-MM-DD format") from None
    if (
        first < date(2019, 1, 1)
        or not 0 <= (last - first).days < MAX_ROWS
        or last > datetime.now(UTC).date()
    ):
        raise SourceError("Choose a historical range from 2019 onward with at most 5,000 days")
    clause = f"portid = '{port}' AND date >= DATE '{first.isoformat()}' AND date <= DATE '{last.isoformat()}'"
    records = []
    acquired = datetime.now(UTC)
    for page in range(5):
        query = urllib.parse.urlencode(
            {
                "f": "json",
                "where": clause,
                "outFields": ",".join(PORTWATCH_FIELDS),
                "orderByFields": "date ASC,ObjectId ASC",
                "returnGeometry": "false",
                "resultRecordCount": 1000,
                "resultOffset": page * 1000,
            }
        )
        result = _json(_download(PORTWATCH_LAYER + "/query?" + query))
        if (
            not isinstance(result, dict)
            or result.get("error")
            or not isinstance(result.get("features"), list)
        ):
            raise SourceError(
                "PortWatch returned an error or an unexpected schema; check its availability and date/port selection"
            )
        batch = result["features"]
        if len(batch) > 1000:
            raise SourceError("PortWatch exceeded the requested page size")
        try:
            for feature in batch:
                attributes = feature["attributes"]
                row = {key: attributes[key] for key in PORTWATCH_FIELDS}
                day = date.fromisoformat(row["date"])
                observed = datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(
                    days=1
                )
                if row["portid"].lower() != port or not first <= day <= last:
                    raise ValueError("Returned row outside requested filter")
                for field in ("portcalls", "import", "export"):
                    value = row[field]
                    if (
                        isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not math.isfinite(value)
                        or value < 0
                    ):
                        raise ValueError("Invalid maritime estimate")
                if observed <= acquired:
                    row.update(observed_at=observed.isoformat(), available_at=acquired.isoformat())
                    records.append(row)
        except (ValueError, TypeError, KeyError, AttributeError):
            raise SourceError(
                "PortWatch returned incomplete or malformed daily observations"
            ) from None
        if not result.get("exceededTransferLimit", False):
            break
        if not batch or page == 4:
            raise SourceError(
                "PortWatch query exceeds the bounded five-page limit; narrow the date range"
            )
    if not records:
        raise SourceError("No completed daily observations matched this port and date range")
    stamps = [row["date"] for row in records]
    if len(stamps) != len(set(stamps)) or stamps != sorted(stamps):
        raise SourceError("PortWatch returned duplicate or unordered daily observations")
    return {
        "source": "portwatch",
        "name": f"IMF PortWatch - {records[0]['portname']}",
        "format": "json",
        "content": json.dumps(records, allow_nan=False, separators=(",", ":")),
        "records": records,
        "columns": list(records[0]),
        "provenance": {
            "provider": "IMF PortWatch / UN Global Platform",
            "url": PORTWATCH_LAYER,
            "fetched_at": acquired.isoformat(),
            "port_id": port,
            "start": first.isoformat(),
            "end": last.isoformat(),
            "authentication": "none",
            "attribution": "Sources: UN Global Platform; IMF PortWatch (portwatch.imf.org).",
            "terms": "https://www.imf.org/external/terms.htm",
            "point_in_time": False,
            "storage": "session only; no operator transmission",
        },
        "mapping_suggestion": {
            "timestamp_column": "observed_at",
            "available_at_column": "available_at",
            "field_columns": ["portcalls", "import", "export"],
            "availability_mode": "column",
            "acquired_at": acquired.isoformat(),
        },
        "warnings": [
            "PortWatch values are revised AIS-derived estimates of maritime activity, not customs trade totals or a live vessel feed.",
            "Historical publication vintages are unavailable in this connector. available_at is acquisition time, so these values cannot trigger historical trades before download. An assumed historical lag is an explicitly exploratory scenario, not a point-in-time backtest.",
            "Respect IMF source-specific terms and attribution. Public/keyless access is not a claim of unrestricted redistribution or commercial licensing.",
        ],
    }


def fetch_source(config: dict, credential: str | None = None) -> dict:
    """Fetch into memory on the local host; never store source keys or observations."""
    if not isinstance(config, dict):
        raise SourceError("Choose a data source configuration")
    identity = config.get("id", config.get("source"))
    if identity == "worldbank":
        return _worldbank(config)
    if identity == "socrata":
        return _socrata_data(config, credential)
    if identity == "portwatch":
        return _portwatch(config)
    if identity in {"custom_https", "http"}:
        return _custom(config, credential)
    if identity == "aisstream":
        raise SourceError(
            "AISStream requires your own account key and a live WebSocket collector. It does not supply historical training records through this app. Import historical observations or use another documented provider."
        )
    if identity in {"nasa", "reference", "space_reference", "europa", "hdx", "auto"}:
        raise SourceError(
            "This selection is discovery metadata or a reference. Choose a supported public table resource, or obtain and explicitly extract timestamped observations from its publisher; no history or satellite events are fabricated."
        )
    raise SourceError("Choose a catalog source or configure a public HTTPS CSV/JSON endpoint")


_indicator_cache: tuple[float, list] = (0.0, [])


def _wb_response(url: str) -> tuple[dict, list]:
    result = _json(_download(url))
    if (
        not isinstance(result, list)
        or len(result) != 2
        or not isinstance(result[0], dict)
        or not isinstance(result[1], list)
        or len(result[1]) > 1000
        or any(not isinstance(item, dict) for item in result[1])
    ):
        raise SourceError("World Bank returned an unavailable or malformed indicator response")
    metadata = dict(result[0])
    metadata["pages"] = _source_int(metadata.get("pages", 1), "World Bank page count", 1, 1000)
    return metadata, result[1]


def _label(value: Any) -> str:
    if isinstance(value, str):
        return re.sub(r"<[^>]*>", " ", value).strip()
    if isinstance(value, dict):
        return _label(
            value.get("en")
            or value.get("title")
            or value.get("label")
            or value.get("name")
            or next(iter(value.values()), "")
        )
    if isinstance(value, list):
        return "; ".join(_label(item) for item in value[:3])
    return ""


def _relevance(query: str, dataset: dict) -> dict:
    stop = set(
        "the a an and or of for in on to by from with when than if then buy sell market bitcoin stock price data dataset number many how more less over under new york jersey ny nj vs versus count compare change rising falling using during between".split()
    )

    def stem(word):
        return word[:-1] if word.endswith("s") and len(word) > 4 else word

    words = {
        stem(word) for word in re.findall(r"[a-z][a-z0-9]+", query.casefold()) if word not in stop
    }
    title = _label(dataset.get("title", "")).casefold()
    body = (title + " " + _label(dataset.get("description", ""))).casefold()
    tokens = {stem(word) for word in re.findall(r"[a-z][a-z0-9]+", body)}
    matched = words & tokens
    space_words = {"satellite", "orbit", "orbital", "spacecraft", "tle", "overpass"}
    space_query = bool(words & space_words)
    space_match = bool(tokens & space_words)
    score = len(matched) * 4 + sum(word in title for word in matched) * 3
    if space_query:
        score += 20 if space_match else -30
    exact = (
        bool(words) and words <= tokens and dataset.get("downloadable", bool(dataset.get("config")))
    )
    match = "exact" if exact else "related" if matched or space_query and space_match else "weak"
    if space_query and not space_match:
        match = "weak"
    return {
        "match": match,
        "score": score,
        "reason": "Metadata matches the requested terms; verify the actual measurement, units and timing."
        if exact
        else "Related concept/domain; additional definition or extraction is required. It is not an exact measured series."
        if match == "related"
        else "Weak metadata overlap or geography only; do not substitute this for the requested phenomenon.",
    }


def _space_references(query: str) -> list[dict]:
    if not re.search(r"satellit|orbit|spacecraft|overpass|\btle\b", query, re.I):
        return []
    return [
        {
            "id": "celestrak-reference",
            "title": "CelesTrak satellite catalog and orbital elements (reference)",
            "description": "Official current satellite catalog and general perturbation orbital elements. A satellite pass over a chosen area needs a defined region, historical orbit vintages and an explicit propagation/event extraction method. Current orbital elements are not past pass-event history.",
            "provider": "CelesTrak",
            "page": "https://celestrak.org/satcat/search.php",
            "url": "https://celestrak.org/NORAD/documentation/gp-data-formats.php",
            "format": "reference",
            "license": "Review CelesTrak data use and service terms",
            "access": "Publisher reference; no automatic historical event extraction",
            "key_required": False,
            "downloadable": False,
            "data_kind": "orbital_catalog_reference",
            "config": None,
            "limitations": [
                "This app does not propagate orbits or derive historical satellite passes. Import an authorized timestamped pass-event table with availability times for that experiment."
            ],
            "curated_reference": True,
        }
    ]


def _nasa_search(query: str, limit: int) -> tuple[list[dict], Any]:
    result = _json(
        _download(
            "https://cmr.earthdata.nasa.gov/search/collections.json?"
            + urllib.parse.urlencode({"keyword": query, "page_size": limit})
        )
    )
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("feed"), dict)
        or not isinstance(result["feed"].get("entry"), list)
    ):
        raise SourceError("NASA CMR returned an unavailable or malformed collection search")
    datasets = []
    for item in result["feed"]["entry"][:limit]:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("id"), str)
            or not re.fullmatch(r"C\d+-[A-Za-z0-9_]+", item["id"])
        ):
            continue
        identity = item["id"]
        datasets.append(
            {
                "id": identity,
                "title": _label(item.get("title", item.get("dataset_id", identity)))[:250],
                "description": _label(item.get("summary", ""))[:1200],
                "provider": _label(item.get("data_center", "NASA Earthdata")),
                "url": f"https://cmr.earthdata.nasa.gov/search/concepts/{identity}.html",
                "page": f"https://cmr.earthdata.nasa.gov/search/concepts/{identity}.html",
                "format": "collection metadata",
                "license": "Collection-specific access/use and attribution terms; inspect publisher",
                "access": "Public discovery metadata; actual data may require your Earthdata account or extraction",
                "key_required": False,
                "downloadable": False,
                "data_kind": "earth_observation_collection",
                "temporal": {"start": item.get("time_start"), "end": item.get("time_end")},
                "platforms": item.get("platforms", [])[:20]
                if isinstance(item.get("platforms"), list)
                else [],
                "config": None,
                "limitations": [
                    "Collection metadata is not a numeric training series. Binary imagery, NetCDF/HDF and historical orbital pass extraction are not implemented; use publisher tools and import documented features."
                ],
            }
        )
    return datasets, None


def _ckan_search(query: str, catalog_name: str, limit: int) -> tuple[list[dict], Any]:
    endpoint = (
        "https://data.europa.eu/api/hub/search/ckan/package_search"
        if catalog_name == "europa"
        else "https://data.humdata.org/api/3/action/package_search"
    )
    result = _json(_download(endpoint + "?" + urllib.parse.urlencode({"q": query, "rows": limit})))
    if (
        not isinstance(result, dict)
        or result.get("success") is not True
        or not isinstance(result.get("result"), dict)
        or not isinstance(result["result"].get("results"), list)
    ):
        raise SourceError("The selected public catalog returned an unavailable or malformed search")
    datasets = []
    for item in result["result"]["results"][:limit]:
        if not isinstance(item, dict) or item.get("private") is True:
            continue
        identity = item.get("id", item.get("name"))
        if not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,150}", identity):
            continue
        translations = item.get("translation", {})
        english = translations.get("en", {}) if isinstance(translations, dict) else {}
        title = (
            _label(item.get("title"))
            or _label(english.get("title") if isinstance(english, dict) else "")
            or identity
        )
        description = _label(item.get("notes", item.get("description", ""))) or _label(
            english.get("notes") if isinstance(english, dict) else ""
        )
        resources, usable = [], None
        for resource in (
            item.get("resources", [])[:50] if isinstance(item.get("resources"), list) else []
        ):
            if not isinstance(resource, dict):
                continue
            format_name = (
                _label(resource.get("format", ""))
                .casefold()
                .replace("application/", "")
                .replace("text/", "")
            )
            format_name = {
                "jsonl": "ndjson",
                "x-ndjson": "ndjson",
                "tab-separated-values": "tsv",
                "geo+json": "geojson",
            }.get(format_name, format_name)
            link = resource.get("download_url", resource.get("url", resource.get("access_url", "")))
            if isinstance(link, list):
                link = link[0] if len(link) == 1 else ""
            if isinstance(link, str) and link.startswith("[https://") and link.endswith("]"):
                link = link[1:-1]
            safe = False
            try:
                _, link = _url(link)
                # Keep query parameters in the actual explicitly selected download, but never in provenance.
                actual = resource.get(
                    "download_url", resource.get("url", resource.get("access_url", ""))
                )
                if (
                    isinstance(actual, str)
                    and actual.startswith("[https://")
                    and actual.endswith("]")
                ):
                    actual = actual[1:-1]
                safe = isinstance(actual, str)
            except SourceError:
                actual = ""
            supported = (
                safe
                and format_name in {"csv", "tsv", "json", "ndjson", "geojson"}
                and not item.get("is_requestdata_type")
            )
            resources.append(
                {
                    "title": _label(resource.get("name", resource.get("description", "")))[:200],
                    "format": format_name,
                    "url": link if safe else "",
                    "supported": supported,
                }
            )
            if supported and usable is None:
                usable = {
                    "id": "custom_https",
                    "url": actual,
                    "format": format_name,
                    "auth": "none",
                }
        page = (
            f"https://data.europa.eu/data/datasets/{identity}"
            if catalog_name == "europa"
            else f"https://data.humdata.org/dataset/{item.get('name', identity)}"
        )
        datasets.append(
            {
                "id": f"{catalog_name}:{identity}",
                "title": title[:250],
                "description": description[:1200],
                "provider": _label(item.get("publisher", item.get("organization", "")))[:250]
                or catalog_name,
                "page": page,
                "url": usable["url"] if usable else page,
                "format": usable["format"] if usable else "publisher resources",
                "license": _label(item.get("license_title", item.get("license_id", "")))
                or "Publisher/resource-specific; inspect source terms",
                "access": "Public metadata; file availability, account, quota and terms depend on publisher",
                "key_required": False,
                "config": usable,
                "downloadable": usable is not None,
                "data_kind": "public_dataset",
                "resources": resources,
                "limitations": [
                    "Only an explicitly selected supported public HTTPS text resource can be downloaded within 4 MB/5,000 rows. Compressed archives, rasters, spreadsheets and other binary formats need external extraction. Catalog metadata dates do not prove historical feature publication times."
                ],
            }
        )
    return datasets, result["result"].get("count")


def search_sources(query: str, catalog_name: str = "socrata", limit: int = 12) -> dict:
    """Search real public catalogs, returning candidates rather than invented datasets."""
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= 200:
        raise SourceError("Enter a data search phrase of 2..200 characters")
    limit = _source_int(limit, "Search result limit", 1, 20)
    query = query.strip()
    datasets = []
    extra_warnings, searched = [], [catalog_name]
    effective_queries = {catalog_name: query}
    concept_query = (
        "satellite orbit"
        if re.search(r"satellit|orbit|spacecraft|overpass|\btle\b", query, re.I)
        and len(query.split()) > 3
        else query
    )
    if catalog_name == "auto":
        secondary = (
            "nasa"
            if re.search(r"satellit|orbit|spacecraft|overpass|\btle\b", query, re.I)
            else "worldbank"
            if re.search(r"gdp|inflation|urban|econom|population growth", query, re.I)
            else "hdx"
        )
        searched = [secondary, "europa", "socrata"]
        effective_queries = {}

        def run(name):
            try:
                return name, search_sources(query, name, min(limit, 8)), None
            except SourceError as error:
                return name, None, str(error)

        with ThreadPoolExecutor(max_workers=3) as executor:
            for name, result, error in executor.map(run, searched):
                if result is not None:
                    datasets.extend(result["datasets"])
                    effective_queries.update(result.get("effective_queries", {}))
                else:
                    extra_warnings.append(f"{name} could not be searched: {error}")
        datasets.extend(_space_references(query))
        total = None
    elif catalog_name in {"europa", "hdx"}:
        effective_queries[catalog_name] = concept_query
        datasets, total = _ckan_search(concept_query, catalog_name, limit)
    elif catalog_name == "nasa":
        effective_queries[catalog_name] = concept_query
        datasets, total = _nasa_search(concept_query, limit)
        datasets.extend(_space_references(query))
    elif catalog_name == "socrata":
        url = "https://api.us.socrata.com/api/catalog/v1?" + urllib.parse.urlencode(
            {"q": query, "limit": int(limit), "only": "datasets"}
        )
        result = _json(_download(url))
        if not isinstance(result, dict) or not isinstance(result.get("results"), list):
            raise SourceError(
                "The public catalog search is unavailable or changed its response format"
            )
        for item in result["results"][:limit]:
            if not isinstance(item, dict):
                continue
            resource, meta = item.get("resource", {}), item.get("metadata", {})
            if not isinstance(resource, dict) or not isinstance(meta, dict):
                continue
            identity, domain = resource.get("id", ""), meta.get("domain", "")
            if (
                not isinstance(identity, str)
                or not isinstance(domain, str)
                or not re.fullmatch(r"[a-z0-9]{4}-[a-z0-9]{4}", identity)
                or not re.fullmatch(r"[A-Za-z0-9.-]+", domain)
            ):
                continue
            try:
                _url(f"https://{domain}/")
            except SourceError:
                continue
            page_url = f"https://{domain}/d/{identity}"
            datasets.append(
                {
                    "id": identity,
                    "title": str(resource.get("name", identity))[:250],
                    "description": re.sub(r"<[^>]*>", " ", str(resource.get("description", "")))[
                        :1200
                    ],
                    "url": f"https://{domain}/resource/{identity}.json",
                    "page": page_url,
                    "format": "json",
                    "provider": domain,
                    "license": str(
                        meta.get("license", "Publisher-specific; inspect the dataset page")
                    ),
                    "access": "Public catalog; download availability and quota depend on publisher",
                    "key_required": False,
                    "columns": [
                        name[:250]
                        for name in resource.get("columns_field_name", [])
                        if isinstance(name, str)
                    ][:100]
                    if isinstance(resource.get("columns_field_name", []), list)
                    else [],
                    "config": {
                        "id": "socrata",
                        "domain": domain,
                        "dataset_id": identity,
                        "limit": 1000,
                    },
                }
            )
        total = result.get("resultSetSize")
    elif catalog_name == "worldbank":
        global _indicator_cache
        cached_at, indicators = _indicator_cache
        if not indicators or time.monotonic() - cached_at > 900:
            indicators = []
            for page in range(1, 4):
                meta, values = _wb_response(
                    f"https://api.worldbank.org/v2/indicator?source=2&format=json&per_page=1000&page={page}"
                )
                indicators.extend(values)
                if page >= meta["pages"]:
                    break
            _indicator_cache = (time.monotonic(), indicators)
        words = re.findall(r"[a-z0-9]+", query.casefold())
        scored = []
        for item in indicators:
            title = str(item.get("name", ""))
            text = (title + " " + str(item.get("sourceNote", ""))).casefold()
            score = sum((3 if word in title.casefold() else 1) for word in words if word in text)
            if score:
                scored.append((score, item))
        for _, item in sorted(scored, key=lambda pair: (-pair[0], str(pair[1].get("id"))))[:limit]:
            identity = item.get("id", "")
            if not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", identity):
                continue
            datasets.append(
                {
                    "id": identity,
                    "title": item.get("name", identity),
                    "description": str(item.get("sourceNote", ""))[:1200],
                    "provider": str(item.get("sourceOrganization", "World Bank / source agencies")),
                    "license": "World Bank and source-specific data terms; inspect indicator attribution",
                    "url": f"https://api.worldbank.org/v2/country/USA/indicator/{identity}?format=json",
                    "page": f"https://data.worldbank.org/indicator/{identity}",
                    "format": "json",
                    "access": "No API key; usually annual revised indicators",
                    "key_required": False,
                    "config": {
                        "id": "worldbank",
                        "indicator": identity,
                        "country": "USA",
                        "start": "2000",
                        "end": "2024",
                    },
                }
            )
        total = len(scored)
    else:
        raise SourceError(
            "Choose auto, socrata, worldbank, europa, hdx or nasa for discovery; other repositories can use their documented public HTTPS table API"
        )
    datasets = list({(item.get("provider", ""), item["id"]): item for item in datasets}.values())
    for dataset in datasets:
        dataset.setdefault("downloadable", bool(dataset.get("config")))
        dataset.setdefault("data_kind", "tabular")
        dataset.setdefault("limitations", [])
        dataset["relevance"] = _relevance(query, dataset)
    datasets.sort(key=lambda item: (-item["relevance"]["score"], item["title"]))
    datasets = datasets[:limit]
    return {
        "query": query,
        "catalog": catalog_name,
        "datasets": datasets,
        "total_matches": total,
        "catalogs_searched": searched,
        "effective_queries": effective_queries,
        "warnings": extra_warnings
        + [
            "Long satellite/region questions are broadened to satellite orbit in domain catalogs; effective_queries records the exact query used. Related collections are not substituted for historical pass events.",
            "Search results are candidate sources, not proof that they measure your requested concept. Check units, geography, time coverage, availability times and license.",
            "A permit, inspection or venue count is not a sales series. Do not silently substitute proxies. Private merch/shop sales normally require the owner's export or authorized API key.",
            "Search/fetch requests run from this local app to the chosen catalog/provider. No application-operator service receives your query, data or keys.",
        ],
    }


def _socrata_data(config: dict, credential: str | None) -> dict:
    domain, identity = config.get("domain", ""), config.get("dataset_id", "")
    if (
        not isinstance(domain, str)
        or not re.fullmatch(r"[A-Za-z0-9.-]+", domain)
        or not re.fullmatch(r"[a-z0-9]{4}-[a-z0-9]{4}", str(identity))
    ):
        raise SourceError("Select a valid catalog dataset and publisher domain")
    limit = _source_int(config.get("limit", 1000), "Download row limit", 1, MAX_ROWS)
    query = {"$limit": limit, "$order": ":id"}
    if config.get("where"):
        if not isinstance(config["where"], str) or len(config["where"]) > 1000:
            raise SourceError("Use a source filter of at most 1,000 characters")
        query["$where"] = config["where"]
    output = _custom(
        {
            "url": f"https://{domain}/resource/{identity}.json?" + urllib.parse.urlencode(query),
            "format": "json",
            "auth": "api_key" if credential else "none",
            "header_name": "X-App-Token",
        },
        credential,
    )
    output.update(source="socrata", name=f"Public dataset {domain}/{identity}")
    output["warnings"].append(
        f"Bounded preview/download of at most {limit} records; the selected source may have more data. Inspect source filters and timestamps before treating it as a complete historical sample."
    )
    return output


def _worldbank(config: dict) -> dict:
    country, indicator = config.get("country", "USA"), config.get("indicator", "")
    if not re.fullmatch(r"[A-Za-z]{2,3}", str(country)) or not re.fullmatch(
        r"[A-Za-z0-9_.-]{3,100}", str(indicator)
    ):
        raise SourceError("Choose one country code and an exact indicator ID")
    start = _source_int(config.get("start", 2000), "Start year", 1960, datetime.now(UTC).year)
    end = _source_int(
        config.get("end", datetime.now(UTC).year - 1), "End year", 1960, datetime.now(UTC).year
    )
    if start > end or end - start > 150:
        raise SourceError("Choose a supported annual indicator range from 1960 onward")
    url = (
        f"https://api.worldbank.org/v2/country/{country}/indicator/{indicator}?"
        + urllib.parse.urlencode({"format": "json", "date": f"{start}:{end}", "per_page": 200})
    )
    _, values = _wb_response(url)
    acquired = datetime.now(UTC).isoformat()
    records = []
    years: set[int] = set()
    for item in values:
        value = item.get("value")
        year = str(item.get("date", ""))
        if (
            not year.isdigit()
            or len(year) != 4
            or not start <= int(year) <= end
            or int(year) in years
        ):
            raise SourceError(
                "The indicator contains duplicate dates or dates outside the requested period"
            )
        years.add(int(year))
        if value is None:
            continue
        if (
            int(year) >= datetime.now(UTC).year
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise SourceError(
                "The indicator contains incomplete annual periods or unsupported values; select completed historical years"
            )
        observed = datetime(int(year) + 1, 1, 1, tzinfo=UTC).isoformat()
        records.append(
            {
                "observed_at": observed,
                "available_at": acquired,
                str(indicator): value,
                "country": country,
                "year": int(year),
            }
        )
    records.sort(key=lambda row: row["observed_at"])
    if not records:
        raise SourceError("No observations exist for that indicator, country and period")
    return {
        "source": "worldbank",
        "name": f"World Bank {indicator} / {country}",
        "format": "json",
        "records": records,
        "content": json.dumps(records, separators=(",", ":")),
        "provenance": {
            "provider": "World Bank / source agencies",
            "url": url.split("?")[0],
            "fetched_at": acquired,
            "point_in_time": False,
            "terms": "https://data.worldbank.org/summary-terms-of-use",
        },
        "mapping_suggestion": {
            "observed_at_column": "observed_at",
            "available_at_column": "available_at",
            "field_columns": [indicator],
            "availability_mode": "column",
            "max_age_hours": 9000,
        },
        "warnings": [
            "Annual revised indicator, not a contemporaneous real-time observation. Availability is acquisition time unless you explicitly select an exploratory historical lag assumption.",
            "Check each source agency's attribution and redistribution terms. Annual data requires compatible dates/frequency; short daily fixture periods may be unsuitable.",
        ],
    }
