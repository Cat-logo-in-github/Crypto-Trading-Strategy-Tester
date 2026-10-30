# Five real public-data exploratory trials — 2026-10-30

Actual public data, exploratory retrospective tests; not verified point-in-time edge evidence.

Market: 274 actual Coinbase Exchange BTC-USD daily bars. Rules use the available sample; the trained model trades only its final held-out portion. The benchmark always uses the same actual evaluation window and costs.

| Question | Strategy | Matched buy/hold | Fills | Fee stress return |
| --- | ---: | ---: | ---: | ---: |
| Rubber-duck debugging rally | -3.61% | 21.24% | 204 | -6.51% |
| Toilet-paper panic scroll | -0.10% | 21.24% | 95 | -1.34% |
| Sourdough predicts panic browsing | 0.00% | 0.85% | 0 | 0.00% |
| Rain in the desert | -0.39% | 21.24% | 39 | -0.82% |
| A shaky planet and digital gold | 0.00% | 21.24% | 0 | 0.00% |

Trading fee scenario is 90 bps per fill, full spread 10 bps, extra slippage 5 bps; 100 ms data and 250 ms order delay. Daily-bar quantization applies. Stress doubles the fee to 180 bps; other settings stay fixed. These are assumptions, not a verified 2025 venue-fee archive.

## Definitions and evaluation windows

### Rubber-duck debugging rally

{"entry": "col('duck_views') > mean(col('duck_views'), 7)", "exit": "col('duck_views') < mean(col('duck_views'), 7)", "sizing": "cash", "weight": 1.0, "signals": [], "amount": 100.0}
Evaluation: 2025-01-01T00:00:00+00:00 to 2025-10-02T00:00:00+00:00; 274 valued bars. Fees: 295.55 USD; maximum drawdown -3.74%. Future-publication negative control: {'fills': 0, 'blocked_future_data': True}.

### Toilet-paper panic scroll

{"entry": "pct_change(col('paper_views'), 7) > 0.1", "exit": "pct_change(col('paper_views'), 7) < -0.05", "sizing": "cash", "weight": 1.0, "signals": [], "amount": 100.0}
Evaluation: 2025-01-01T00:00:00+00:00 to 2025-10-02T00:00:00+00:00; 274 valued bars. Fees: 124.90 USD; maximum drawdown -0.60%. Future-publication negative control: {'fills': 0, 'blocked_future_data': True}.

### Sourdough predicts panic browsing

"Explicit reviewed natural-language target: predict whether the available toilet-paper pageviews will exceed their trailing seven-bar average three bars ahead, using sourdough and rubber-duck interest; target 50% BTC when probability exceeds .55."
Evaluation: 2025-08-08T00:00:00+00:00 to 2025-10-02T00:00:00+00:00; 55 valued bars. Fees: 0.00 USD; maximum drawdown 0.00%. Future-publication negative control: {'blocked_future_data': True, 'error': 'Need at least 12 train, 6 validation and 6 test rows after missing-value filtering and horizon purging'}.

### Rain in the desert

{"entry": "col('rain_mm') > 0.1", "exit": "col('rain_mm') < 0.1", "sizing": "cash", "weight": 1.0, "signals": [], "amount": 100.0}
Evaluation: 2025-01-01T00:00:00+00:00 to 2025-10-02T00:00:00+00:00; 274 valued bars. Fees: 42.85 USD; maximum drawdown -0.40%. Future-publication negative control: {'fills': 0, 'blocked_future_data': True}.

### A shaky planet and digital gold

{"entry": "col('event_count') > mean(col('event_count'), 7)", "exit": "col('event_count') < mean(col('event_count'), 7)", "sizing": "cash", "weight": 1.0, "signals": [], "amount": 100.0}
Evaluation: 2025-01-01T00:00:00+00:00 to 2025-10-02T00:00:00+00:00; 274 valued bars. Fees: 0.00 USD; maximum drawdown 0.00%. Future-publication negative control: {'fills': 0, 'blocked_future_data': True}.

## Publication assumptions

- Wikimedia days are measured at UTC day completion; an explicit additional 48-hour historical lag is assumed, not verified release vintages. Counts reflect the retrieved archive and may be revised.
- Open-Meteo reanalysis days complete at UTC day end; a seven-day lag is only an exploratory scenario, not a reconstruction of forecast/reanalysis vintages. This trial trades reported rainfall, not forecast skill.
- USGS uses supplied actual last-update timestamps; daily event counts become eligible only after the completed bucket and every included update. Historical revisions published after the test period are excluded. Count reflects the complete returned query, not a live original-release archive.
- All five thresholds and model settings were fixed before these fetched returns were inspected. Five related hypotheses and a single selected period remain multiple exploratory tests.

## Sources

- [market: fetched 17,472 bytes](https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=86400&start=2025-01-01T00:00:00Z&end=2025-10-01T00:00:00Z)
- [duck: fetched 43,229 bytes](https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/Rubber_duck_debugging/daily/2025010100/2025100100)
- [paper: fetched 40,607 bytes](https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/Toilet_paper/daily/2025010100/2025100100)
- [sourdough: fetched 40,015 bytes](https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/Sourdough/daily/2025010100/2025100100)
- [weather: fetched 7,716 bytes](https://archive-api.open-meteo.com/v1/archive?latitude=36.17&longitude=-115.14&start_date=2025-01-01&end_date=2025-10-01&daily=precipitation_sum,sunshine_duration&timezone=UTC)
- [quakes: fetched 4,743,753 bytes](https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&starttime=2025-01-01&endtime=2025-10-01&minmagnitude=4.5&orderby=time-asc&limit=20000)
- [quake_count: fetched 4 bytes](https://earthquake.usgs.gov/fdsnws/event/1/count?starttime=2025-01-01&endtime=2025-10-01&minmagnitude=4.5)

## Limits

- No actual private sales, borrowing data, options chains, funding tape or professional broker entitlement was supplied.
- These actual-data tests use the declared coarse bar backend; fine-event and multi-contract paths are independently tested with controlled quote/cash-flow fixtures.
- No threshold was tuned to improve the reported test returns. Three predeclared model penalties use validation only; final model return is held-out. Positive historical return is not evidence of repeatable future profitability.

Full metrics, paired block-bootstrap uncertainty, model diagnostics, query URLs and raw-data hashes are in [full JSON evidence](public-strategy-results.json). Raw downloaded datasets and full intermediate payloads stay in work/, outside the release ZIP.