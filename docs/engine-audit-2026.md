# Current execution-engine audit, 2026-10-29

This is a separate review pass over the active Hypothesis Lab engine, data boundary and rule path, rather than a repeat of the original repository audit. Findings below distinguish reproduced defects, tested accounting behavior and unresolved modeling limits. It is a code/test review, not an exchange certification or evidence of a profitable strategy.

## Findings and changes

| Area reviewed | Evidence and result |
| --- | --- |
| Existing accounting | Original-capital total return, average cost basis, proportional buy/sell commission, post-cost target exposure and compatible buy-and-hold were retained. Existing hand calculations and seeded cash/unit reconciliation tests pass. Realized gains are not added twice to cash. |
| Timing realism | The prior active path always executed the previous completed bar's decision at the next supplied open. That was an explicit zero-delay assumption, not a measured execution model. It had no configurable publication/inference/submit queue. The new path schedules actual eligibility and changes both fill price and the time cash/units change. |
| Fixed and spread costs | The prior path modeled proportional commission and slippage only. The new path adds quote-currency fixed commission, a full spread assumption and separate cost breakdowns, with cash constraints and cost-aware target sizing. These are modeled assumptions, not observed quotes. |
| Very small fractional positions | Reproduced defect: a fixed `1e-10` quantity cutoff discarded a valid $1 purchase at a $1 trillion reference price. The engine now applies a tiny notional-relative numerical tolerance. This does not implement venue lot/minimum-order rules. |
| External feature names | Reproduced defect: an aligned external column called `close` could override the market close in a rule. Reserved market features now take precedence; `event:close` explicitly selects that external field. |
| Input ambiguity | Duplicate CSV headers previously allowed the CSV reader to overwrite a column silently. They now fail validation. Boolean prices and invalid timestamp object types also fail explicitly. |
| Numeric edge cases | A complete equity loss followed by another bar now produces total return/drawdown of -100% and undefined later risk ratios, rather than dividing by zero. Finite-value guards prevent exporting nonfinite portfolio arithmetic. Large finite moving averages avoid unnecessary sum overflow. |
| Evaluation periods | Engine bounds retain complete input history for feature warmup while trading only within an explicit evaluation window. Prior intents are ignored, outstanding intents expire at the end, and the benchmark uses the same window and costs. |

The added regression suite is `tests/test_engine_audit.py`. It uses explicit clock/price examples, independent fee-inclusive cash calculations, partial sales, capital identities and seeded paths. The original `test_core.py`, `test_ml.py` and `test_rl.py` suites were also executed during this pass. Their counts and final integrated verification belong in the implementation status; do not infer that remote CI or live venue execution occurred.

## Execution clock and queue

`Bar.timestamp` is the opening timestamp. Its nominal close is `timestamp + bar_seconds`. The configured data delay determines when that completed bar becomes available. An optional `Decision.available_at` can declare later inference or other readiness; it cannot make the decision earlier than the completed bar's availability.

```text
nominal_close = source_bar_open + bar_seconds
market_available_at = nominal_close + data_delay_ms
decision_at = max(market_available_at, explicit_available_at_if_supplied)
eligible_at = decision_at + latency_ms
fill = first supplied later bar open at or after eligible_at
```

Positive fractional delays round upward to the datetime clock's microsecond resolution. They do not silently vanish at a boundary. Fills and `order_events` record the source-bar open, nominal close, market availability, decision/submission time, eligibility and actual fill time. Legacy `orders` retain their original summary fields. An intent with no remaining eligible open expires without a fill or fee.

Example: with one-second bars, the first close is at 00:00:01. A 1 ms submit delay makes the 00:00:01 open ineligible, so the fill uses the 00:00:02 open and its price. The portfolio stays unchanged until then. A timestamp-only relabeling would incorrectly keep the earlier price and earlier cash movement.

This is still a **bar-resolution approximation**. A small positive delay at a daily boundary can defer an entire day because there is no intervening quote in the supplied data. The timing rule is conservative about when the next represented opportunity can be used; it is not guaranteed to worsen price or performance. It does not reconstruct a millisecond market fill. Use finer, appropriately timestamped data when that distinction matters.

Each explicit intent remains pending until eligible or expired. Ready intents execute in readiness order, with source-bar order breaking ties. Multiple accumulation buys are retained. There is no automatic supersession/cancel protocol: an explicitly late older intent can execute after a newer intent. A strategy requiring cancel/replace must implement a corresponding policy before treating this as a broker simulation.

## Cost and position conventions

| Setting | Units and meaning |
| --- | --- |
| `fee_bps` | Proportional market/taker-style commission on actual filled notional; 1 bp = 0.01%. |
| `fixed_fee` | Additional quote-currency charge per successful fill, on buys and sells. Rejected/expired/no-change intents pay none. |
| `spread_bps` | Assumed **full** bid/ask spread; half is applied adversely to each side. |
| `slippage_bps` | Additional adverse price movement beyond the half-spread. |
| `data_delay_ms` | Assumed publication delay after the nominal bar close. |
| `latency_ms` | Assumed delay from decision/submission readiness to venue eligibility. |

Buy price is `open * (1 + spread_bps/20000 + slippage_bps/10000)`; sell price uses the corresponding subtraction. An OHLC open is a reference trade price, not an observed midpoint, so this spread construction is a scenario model. Do not add a spread again if an imported reference already represents the executable side.

Cash budgets include proportional and fixed fees. Target weights are solved against post-cost equity marked at the fill open; they are constrained by available cash and long-only holdings. An unchanged target incurs no fill or fee. If a fixed cost would reverse the direction of the intended adjustment, that adjustment is rejected rather than manufacturing a fee-paying opposite-side trade. Partial sales allocate average entry cost, including entry fees. Sale P&L deducts sale fees. An impossible sale fee cannot create negative cash. All-cash exhaustion is handled explicitly.

Portfolio equity equals cash plus marked holdings; with no external cash flows it also reconciles to initial capital plus cumulative realized and unrealized P&L. Execution costs are already included in cash/filled prices; do not subtract the reported cost breakdown again. Final holdings are marked at the last close and are not forcibly liquidated.

`backtest(..., start_index=..., end_index=...)` and `benchmark` use an inclusive start and exclusive end. They need at least two active bars. The initial portfolio is reset at the active start; earlier history can inform already-computed causal indicators, but earlier intents cannot spend active-period capital. Pass the same bounds to `decisions_for` so a one-shot rule begins its active state in that window instead of consuming its one entry during warmup. The benchmark submits at the first active completed close and uses the same costs/readiness convention. A model's train/validation/test partition remains a separate requirement.

## Dated, editable venue scenarios

`costs.execution_profiles()` returns five profiles with numeric execution fields, source links, an `as_of` date, fee evidence, scope and a separate assumptions list. Applying a named profile copies editable numeric values; the engine does not infer a broker account, fetch a personalized rate, select a tier or change fees automatically. Historical experiments need historically applicable fee schedules; a current snapshot is not such a database.

On 2026-10-29 the rendered official Kraken Spot Crypto table showed Tier 1 ($0+) maker 0.40% and taker 0.80%, with geography/VPN and account-tier caveats. The profile uses 80 bps taker; the older 25/40 bps schedule is not assumed current. [Kraken official fee schedule](https://www.kraken.com/features/fee-schedule).

Binance's regular standard spot row showed 0.100% maker and taker before BNB discounts, pair promotions or account terms. Its profile uses 10 bps taker. [Binance official spot fees](https://www.binance.com/en/fee/trading).

Coinbase's dated 2026-09-16 announcement gives spot entry rates of 0.50% maker/0.90% taker for the US, 0.25%/0.50% for EU/UK, and 0.09%/0.10% for specified other international markets. The included profile is explicitly the US entry example, not a universal Coinbase rate. [Coinbase official fee update](https://www.coinbase.com/blog/were-lowering-fees-for-many-active-traders-on-coinbase-advanced).

The maker rates are context only: this engine has market/taker-style fills and does not simulate passive maker orders. All profile spread, slippage, fixed-fee and delay values are **illustrative assumptions**, not measured venue values. The zero-cost profile is an idealized debugging baseline; the stress profile is a sensitivity case, not a measured worst case or a guarantee of conservatism.

## What measured latency can and cannot establish

The CCXT team's 2026-07-16 measurement reports public order-book request time-to-first-byte from several cities. It shows strong geographic dependence: for example Kraken 16 ms from London versus 268 ms from Sydney, and Coinbase around 10 ms from New York versus 1,109 ms from Sydney in that capture. The authors describe endpoints, repeated rounds and their collector. [Primary measurement and methodology](https://docs.ccxt.com/blog/how-far-is-your-exchange).

These are public-data request measurements, **not** private order-arrival latency, exchange matching delay, model inference time or guaranteed current performance. Do not divide such a round trip by two and call the result an order timestamp. Actual inference/service timings depend on hardware, model, prompt/data size, cache state, load, network path and clock methodology. A present-day endpoint measurement can parameterize an explicit replay scenario; it cannot establish what a historical trader's hardware/model knew or did.

## Remaining scientific and market limits

- **Liquidity:** full fractional fills use an assumed price without depth, market impact, queue priority, partial fills or volume participation. Current-bar total volume is not used to cap a fill at that bar's opening, because that volume would be future information. Large orders and thin markets can be materially misrepresented.
- **Venue rules:** tick sizes, lot steps, minimum notional, fee rounding, fee currency and changing instrument status are not enforced. Real venues define such rules; see [Binance filters](https://developers.binance.com/en/docs/products/spot/filters) and [Kraken asset-pair metadata](https://docs.kraken.com/api-reference/market-data/get-tradable-asset-pairs). Profiles do not make the simulator an exchange adapter.
- **Market scope:** one long-only spot instrument, no leverage, short borrow, funding, dividends/splits, corporate actions, tax, exchange calendars or synchronized multi-asset portfolio model. Price gaps are retained and warned about; missing bars are not fabricated. Frequency-based risk ratios need care with irregular data.
- **Point-in-time data:** separate observation/publication timestamps prevent straightforward future joins only if the source timestamps and revisions are truthful. Revised weather/economic/shipping records and data assembled later can still introduce bias. Retrieval time is not proof of historical availability. Kraken's public OHLC also has finite recent coverage and an uncommitted final candle, as stated in its [official contract](https://docs.kraken.com/api-reference/market-data/get-ohlc-data).
- **Model provenance:** chronological splits and purged labels support controlled in-project training. Uploaded/pretrained models and LLMs can already contain evaluation-era knowledge. A declared `trained_through` date is metadata, not independent proof of training-data vintage. Unknown provenance must remain a historical inference replay, not a verified out-of-sample result.
- **Research selection:** repeated hypotheses, parameter/feature searches and inspection of held-out results can overfit. A useful prediction can lose money after costs, and correlation is not causation. Software tests verify stated mechanics; they do not verify an investment edge.

The defensible conclusion is narrower than "realistic trading": the tested engine now models explicit availability/latency, costs and bounded spot accounting consistently under its declared assumptions. It remains a research simulator with material execution and data limits.
