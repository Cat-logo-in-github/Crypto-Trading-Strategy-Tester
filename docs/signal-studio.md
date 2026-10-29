# From a weird hypothesis to a paper-trading experiment

Hypothesis Lab is a **student project for historical strategy research and simulated paper trading**. It sends no real orders. Its advantage is making unusual measurable ideas quick to express and inspect, while keeping the assumptions visible. It cannot guarantee that every requested dataset exists, interpret every binary format, or establish a scientifically proven trading edge.

## The short path

1. Describe the question. Search across the catalogs or upload your own table/API response. Results label direct, related and weak matches; a shared location is not enough to establish the requested measurement. Satellite collections and current orbital references are distinguished from historical pass-event data.
2. Review the suggested dates, measured fields and entity. Common calendar parts, ISO/Unix dates, wide/long tables, text labels and Point coordinates have guided mappings. Choose the source's actual publication history, acquisition-time eligibility or an explicitly labeled historical-lag assumption. Filtering a specific entity prevents unrelated airport/store/satellite rows from becoming one ambiguous series.
3. Define entry and exit separately. Start with the visual conditions, or describe an algorithm and review its supported draft. The optional model/LLM belongs to you; no weights or SDK are bundled.
4. Select the historical dates or recent-bar duration, the actual bar interval, cash/exposure and costs. Venue profiles contain dated official commissions plus separately marked spread/slippage/latency assumptions. Override every numerical value with your own measurements.
5. Preview the signal, run the experiment and inspect every decision, delayed order, fill and portfolio balance. No trades, missing inputs and rejected orders are results to investigate, not evidence that a strategy is profitable or unprofitable.

## Supported data representations

CSV/TSV, JSON arrays/envelopes, NDJSON and GeoJSON Point/properties are supported as bounded tabular inputs. Numeric/boolean columns work directly; text can become equality/phrase/count/length measurements; categories can be encoded explicitly. Calendar parts and entity filters are guided; event counts/sums/means can be aggregated using explicit UTC windows. See [data interpretation](data-sources.md).

Images, audio, video, raw satellite imagery, shapefiles, Parquet and arbitrary executable model files are not universal native inputs. Use a user-controlled extraction/model service to produce timestamped numeric or event outputs, then import them or connect the service. An arbitrary idea still needs an observable definition, sufficient overlapping history and appropriate market prices. The app does not quietly replace missing satellite passes with airport passengers.

## Small deterministic algorithms

Expressions are parsed with a bounded interpreter. They never use Python `eval`, executable uploads, shell commands or downloaded code. Use `col('column name')` for mapped numeric signals; simple names also work. Available market values are `market.open`, `market.high`, `market.low`, `market.close`, `market.volume` and `market.return_1`, known by the decision close. UTC calendar signals are `hour_utc`, `weekday_utc` (Monday 0) and `month_utc`, evaluated at the completed-bar decision time including the configured data delay. These three names are reserved; rename a measured column that uses one.

Example entry and exit:

```text
Entry: pct_change(col('ice_cream_sales'), 7) > 0.1 and market.close > mean(market.close, 20)
Exit: crosses_below(market.close, mean(market.close, 20))
```

For previously mapped text events `pass_over_ny` and `pass_over_nj`:

```text
Entry: col('pass_over_ny') > 0
Exit: col('pass_over_nj') > 0
```

That example requires actual timestamped pass events with satellite/entity selection, region definitions and historical availability. The expression does not generate orbital history. Alternatively, measured latitude/longitude can be tested against an explicitly chosen box or distance; a box/point-radius is an approximation chosen by the user, not an automatic administrative boundary.

```text
inside_box(col('latitude'), col('longitude'), 40.5, -74.3, 40.9, -73.7)
distance_km(col('latitude'), col('longitude'), 40.7, -74.0) < 10
```

Supported functions: `lag`, `mean`, `sum`, `count`, `difference`, `pct_change`, `zscore`, `crosses_above`, `crosses_below`, `abs`, `sqrt`, `log`, `minimum`, `maximum`, `clip`, `where`, `distance_km` and `inside_box`. Math operators are `+ - * / % **`; comparisons are `> >= < <= == !=`; combine them with `and`, `or`, `not` and parentheses. Trailing windows use literal 1..1,000 supplied market bars. `count` counts true/nonzero conditions in a complete trailing window. `zscore` uses trailing population standard deviation. Longitude boxes can cross the dateline when west exceeds east.

Up to twelve named custom expressions can be chained in order and used as model inputs/targets. Existing field names cannot be overwritten. Expressions have length/depth/complexity bounds and powers are restricted. Unknown fields and executable constructs are rejected. Division by zero, invalid coordinates/math, missing inputs and insufficient trailing history remain missing. Exit takes priority if entry and exit both match; missing conditions hold the current exposure. Repeated cash entries accumulate buys while funds are available.

Natural-language conversion deliberately leaves unresolved definitions visible. The built-in grammar covers simple numeric buy/sell clauses; the user's optional LLM can propose a reviewed expression. Neither path invents a satellite, region boundary, undocumented threshold or source history.

## Periods, clocks and realistic limits

Date-only inputs use UTC. End dates include that complete day, and bars must finish by the selected end. Rules/algorithms retain up to 1,000 earlier bars for indicator warmup but start portfolio accounting and trading inside the selected window. Longer chained windows may still need more history and expose missing signals. Model training periods contain chronological train/validation/held-out evaluation; performance is shown for the held-out portion, rather than silently trading on training rows. Pretrained/service replay can use the selected evaluation window with explicit pretraining and call-budget limits.

Bar-close availability, processing/data delay, optional measured inference duration and submit-to-venue latency determine order readiness. Execution uses the first supplied later open at or after readiness. A 10 ms delay after a daily boundary can therefore skip an entire day: this is a coarse price-observation constraint, not millisecond order-book realism. Use finer bars for latency-sensitive ideas. Delaying a fill is not guaranteed to worsen profit; price may move either way.

Spread, commission, fixed fees and additional adverse slippage are separate costs. There is still no liquidity queue, exchange matching engine, passive maker fill, dynamic market impact, margin/shorting, dividends, corporate-action, tax or survivorship correction. Current fee schedules are not a point-in-time historical fee database. Read the [independent engine audit](engine-audit-2026.md) before using a result as research evidence.

Historical LLM replay can contain future knowledge in model weights. Measured present-day inference duration is an explicit replay assumption, not proof the same model/hardware existed historically. Point-in-time inputs, independent tests, fresh holdouts and sensitivity checks remain the researcher's responsibility.

Entity selection accepts any mapped column. Suggested values come from detected series or preview rows; choose **Enter another exact value** for one outside the preview. CSV identifiers are text; JSON numeric/boolean identifiers retain their types. Composite month fields accept integers and English month names such as Jan, January or Sept. Monthly totals are dated at completion by default; this is separate from their publication time.
