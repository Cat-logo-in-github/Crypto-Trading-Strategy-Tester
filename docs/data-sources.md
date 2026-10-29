# Find data for a question

The workbench is a general data-and-model research tool. A feature can describe weather, road traffic, urban development, retail activity, maritime trade or another measurable concept. The data finder searches real public catalogs and downloads selected records from the local computer. It does not infer that a convenient dataset answers the question, invent missing measurements or promise access to private records.

For example, a count of shops, permits or health inspections does not measure ice-cream or merchandise sales. Actual private sales usually require an owner's export or an authorized provider API. A user may test an explicitly declared proxy, but must label it and explain its limits.

## Search and select

The catalog search has two implemented discovery backends:

| Catalog | Useful starting questions | Access and scope |
| --- | --- | --- |
| Public Socrata catalogs | Traffic, civic activity, environment, permits, businesses and other publisher datasets | Discovery without a key; every publisher sets its own data terms and quotas |
| World Bank indicators | Population, urban growth, transport, climate, development and economic indicators | Keyless API; this release searches World Development Indicators/source 2, not every World Bank collection |

Enter a phrase, inspect candidate descriptions, units, columns, geography, dates and license, then select a source. Empty results mean no suitable candidate was found in that catalog and search scope. Try another phrase, another catalog or the generic HTTPS/import workflow; no substitute is silently selected.

Socrata search returns at most 20 candidates. World Bank searches a bounded metadata index of up to three pages of 1,000 indicators, cached in memory for 15 minutes. Matching uses words in titles and source notes; it is not a semantic search of the entire web. Neither catalog guarantees uptime, complete coverage or that a particular historical series exists. The [Socrata data discovery documentation](https://dev.socrata.com/data/) describes its catalog network; the [World Bank API overview](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation) describes the indicator API.

## Download and map

Downloads are bounded previews or selected periods, not an unlimited crawler. All source records pass through the same mapping workflow as file imports: identify observation time, availability time, numeric/categorical fields, entity/location and expiry before using them in a strategy or model. Select a meaningful target and convert inference into explicit trading rules, separately from the data's subject matter.

The public-source fetchers are:

- **Socrata datasets:** select a discovered publisher domain and dataset ID. Fetch up to 5,000 rows, ordered by the source row ID. An optional source filter can narrow the sample. An owner-provided app token, if necessary, goes only to that publisher in `X-App-Token`. This bounded download may not contain the full historical period; inspect source filters, row counts and timestamps before training.
- **World Bank annual indicators:** choose one country, an exact indicator ID and a year range. Missing values are omitted; duplicate, incomplete or out-of-range years are rejected. An annual observation is dated at the end of its year, not its beginning. Revised annual values are unsuitable for pretending to observe that value continuously during the year. The API's [call-structure documentation](https://datahelpdesk.worldbank.org/knowledgebase/articles/898581-api-basic-call-structures) explains country, indicator, date and pagination parameters.
- **IMF PortWatch:** choose one port ID and a historical date range from 2019 onward. Fetch up to five 1,000-row pages of completed daily port calls and estimated import/export tonnes. `port0` is Abbot Point in the provider's reference catalog. This is one optional example domain, not the product's focus. Its [public daily layer](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Ports_Data/FeatureServer/0) and [port reference](https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/PortWatch_ports_database/FeatureServer/0) expose the schema and IDs.
- **Custom HTTPS CSV/JSON:** enter a documented public HTTPS endpoint. Select CSV or a JSON array path, such as `data.items`; an optional per-record object path, such as `attributes`, selects the tabular record within each array item. This is a single GET with a 4 MB and 5,000-row cap, without automatic pagination. Other repository APIs can use this route or an exported local file.

Existing weather and market connectors remain optional. See [data providers](data-providers.md) for their separate coverage and terms. Arbitrary images, audio, raw AIS streams and unstructured text require a feature-extraction workflow before they become numeric model inputs; the generic tabular mapper does not automatically interpret them.

## When was this information knowable?

World Bank and PortWatch historical values can be revised and their current API responses do not supply the historical publication vintages needed for a strict point-in-time backtest. Their default `available_at` is the time this app acquired the values. This deliberately prevents a newly downloaded revised number from generating a trade years before acquisition.

For exploratory historical research, the user can explicitly choose an assumed publication lag in the common mapping workflow. Such a run is labeled as an availability assumption; a lag is not evidence that those exact revised values existed then. To make a strict historical claim, provide source records with genuine publication/availability timestamps or historical vintages. The IMF's [PortWatch methodology paper](https://www.elibrary.imf.org/view/journals/001/2025/093/article-A001-en.xml) explicitly discusses revisions, AIS coverage limitations and the difference between its estimates and official trade statistics.

An annually sampled feature also needs a compatible experiment horizon, expiry and history length. A few annual values cannot support a meaningful daily prediction exercise merely because the market has many daily bars.

## Credentials, network and retention

Requests go directly from the user's Python process to the selected catalog or provider over verified HTTPS. There is no application-operator backend, relay, hosted credential store or telemetry destination. Source credentials are supplied separately from configuration and are not included in provenance or experiment exports. Common credential fields returned by a provider are removed, and the supplied key is redacted if echoed in data strings.

The generic connector accepts no key, a Bearer token or a named API-key header. If the chosen source requires authentication, the app asks for the user's own key; it does not create an account, buy an entitlement or use the developer's credentials. Keyless access may still have quotas and source-specific restrictions.

API keys in URL queries or embedded URL credentials are rejected. Provenance omits query strings because these can contain private filters. For security, the generic downloader uses public HTTPS on port 443, rejects private/local IP addresses and DNS answers, pins the validated address while verifying the original TLS hostname, ignores proxy environment settings and refuses redirects rather than forwarding credentials. This means an enterprise network that requires a proxy may need a local file export instead. The connector does not bypass certificates or private-network restrictions.

Fetched records and public metadata remain in the app's session memory by default. Closing the app clears them unless the user explicitly saves/exports locally through the workbench. Catalog search phrases are sent to the selected catalog as necessary to perform the search; no claim of provider-side anonymity or zero provider logging is made. The workbench operator receives none of the data or keys. Respect the selected provider's privacy policy as well as its data license.

## Licensing and source limits

Public discovery is not a universal redistribution license. Socrata results show the publisher's reported license or a link to its dataset page; inspect that source's actual conditions. World Bank's [summary terms](https://data.worldbank.org/summary-terms-of-use) generally permit reuse under CC BY 4.0 with required attribution and additional conditions, but individual third-party indicators can have different restrictions. PortWatch's official ArcGIS item links to [IMF terms](https://www.imf.org/external/terms.htm); this release preserves attribution and does not assert unrestricted commercial redistribution. Fetched real datasets are not bundled in the release.

AISStream is listed as an informational live-data reference only. Its [official documentation](https://aisstream.io/documentation) requires an account key and a backend WebSocket subscription, prohibits direct browser connections and offers no durable historical replay. The current workbench does not collect that stream and never represents it as a historical training API.

## Verified behavior

Actual keyless requests from this host succeeded for a Socrata `traffic` search and three-row download (Calgary Traffic Incidents, resource `35ra-9556`), World Bank `USA` / `SP.URB.GROW` for 2020-2022 (three annual observations), and PortWatch `port0` for 1-10 January 2024 (ten daily observations). These probes establish reachability at verification time, not ongoing availability or statistical suitability.

The offline source tests use independent synthetic response shapes to check catalog matching, bounded paging/cache, malformed responses, invalid filters, missing keys, credential redaction, acquired availability, JSON/CSV schema limits, private-address rejection, DNS pinning, redirect refusal, quotas and network errors. They make no external API calls.

## Python source API

```python
from hypothesis_lab.sources import search_sources, fetch_source

candidates = search_sources("urban growth", "worldbank", limit=5)
choice = candidates["datasets"][0]
source = fetch_source({
    **choice["config"],
    "country": "USA",
    "start": "2000",
    "end": "2024",
})
print(source["columns"] if "columns" in source else source["mapping_suggestion"])

# Generic repository/API example; replace with the publisher's documented URL.
# The key stays in the calling session and is never part of source configuration.
# source = fetch_source({
#     "id": "custom_https", "url": "https://publisher.example/data",
#     "format": "json", "records_path": "data.items", "auth": "bearer",
# }, credential=user_supplied_key)
```

`fetch_source` returns `content`, `format`, `records`, `provenance`, `warnings` and mapping suggestions. Discovery returns candidates and their fetch configurations; it does not automatically train on an unreviewed match.
