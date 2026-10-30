# Observed quote, depth and trade replay

This optional backend uses historical execution evidence for one exact long-only spot instrument. The default bar backend remains available when only OHLC exists; it does not fabricate the finer history. For signed/multiple contracts and funding/dividends/margin, use [linked contracts](linked-contracts.md).

## Quick setup

In **New experiment → Period**, open **Optional quote/trade execution replay**, choose CSV/NDJSON, enter the exact instrument and units, set maximum source-quote age, displayed-size participation, quantity step and minimum notional, then enable it. The same rule, model or algorithm decisions run against this history. Upload the matching reference market timeline separately and configure its bar duration. The backend does not search for or silently substitute an exchange tape.

Prices are quote currency per base unit; sizes and order quantities are base units. Timestamps require zones. Provide actual receipt time with `available_at` if known. Otherwise configured data delay is explicitly assumed. Source timestamp controls staleness; availability controls when evidence can be used.

CSV quote example:

```csv
timestamp,available_at,instrument,type,bid,ask,bid_size,ask_size,sequence
2025-01-01T00:00:59Z,2025-01-01T00:00:59.020Z,BTC/USD,quote,99999,100001,0.3,0.2,1
```

NDJSON also supports absolute multi-level depth:

```json
{"timestamp":"2025-01-01T00:01:00Z","instrument":"BTC/USD","type":"depth","bids":[[99999,0.3],[99998,0.7]],"asks":[[100001,0.2],[100002,0.5]],"sequence":2}
```

Trade evidence uses `type:"trade"`, `price`, `quantity`, `aggressor:"buy"|"sell"|"unknown"`. Unknown aggressor does not prove a passive fill. Every event must name the configured instrument. Raw incremental deltas are rejected; assemble validated absolute snapshots outside this adapter. Input limits are 100,000 records, 16 MB text and 200,000 observed levels. Duplicate identities, repeated prices within a side, crossed books, nonfinite values and invalid units fail explicitly.

## API and orders

Add `execution_replay` to the normal research payload:

```json
{
  "instrument":"BTC/USD",
  "format":"ndjson",
  "content":"...",
  "max_quote_age_ms":1000,
  "participation_rate":0.1,
  "quantity_step":0.00000001,
  "min_notional":1,
  "limit_ttl_ms":60000,
  "queue_ahead_multiplier":1
}
```

Use `records` instead of text for canonical event objects. Python exposes `parse_replay`, `ReplayConfig`, `replay_backtest` and `replay_benchmark` in `hypothesis_lab.microstructure`. Evaluation bounds are start-inclusive/end-exclusive; earlier quotes may inform readiness, but prior strategy intents never carry into a fresh evaluation window. The benchmark uses the identical window, data, costs and execution constraints.

The ordinary visual builder emits `Decision` market intents. Market orders are **IOC**: they walk available eligible displayed levels, obey fee-inclusive cash/units and participation limits, partially fill if necessary, then cancel the remainder. Actual bid/ask spread is used once; `ExecutionConfig.spread_bps` is ignored, while extra adverse slippage remains explicit. Fixed commission is charged once per order on its first actual fill. Lot/minimum rules and stale/no-depth conditions can prevent any fill.

Advanced API clients can supply `execution_intents`, one slot per retained reference bar. A limit example is `{order_type:"limit",side:"buy",quantity:0.01,limit_price:99999,ttl_ms:5000,client_id:"L1"}`; cancel with `{cancel_id:"L1"}`. Use canonical JSON with quoted keys when sending. Readiness cannot predate the completed source bar plus data/order delays. Resting orders reserve cash/units, expire at TTL/end, and cancellation/expiry wins ambiguous equal-time trade evidence.

## What the evidence permits

This is a **receipt-time paper replay**, not an exact exchange matching engine. An observation arriving exactly at an order's arrival cannot retrospectively fill that arrival. Delayed print evidence changes cash when it is available, never by backdating. Consumed capacity is retained by side/price across snapshots so unchanged snapshots cannot be reused as unlimited liquidity; this can underfill genuine replenishment.

A passive fill requires subsequent aggressor prints at the exact observed limit price, after explicit assumed queue-ahead quantity is consumed. Printed quantity and queue capacity are consumed once. L2 snapshots do not identify individual orders, cancellations or priority. Queue-ahead multiplier is a scenario, not reconstructed level-3 data. There is no hidden-liquidity prediction or made-up time-priority claim.

Positions are valued at source-bar closes, not forcibly liquidated. Fills contain actual processing/receipt timestamps, nominal readiness, observed spread/depth impact, commissions and residual order status. The output records data level, clock and assumptions. Model decisions are generated once; selecting a finer execution backend does not retrain or select a model using its test P&L.

Fourteen independent regression cases cover parsing/units, depth walks, cash and fee identities, no capacity reuse, partial fills, stale/same-time quotes, delayed availability, lot/minimum rules, queue/print consumption, cancel/TTL ordering, reservations and matched benchmark windows. These tests establish implemented contracts, not verified exchange execution or a profitable edge.
