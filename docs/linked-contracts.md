# Linked contracts and execution evidence

Version 0.4 adds two execution paths beyond the original completed-bar spot path. **New experiment** can replay supplied quotes/depth/trades for one instrument. **Multi-leg contracts** uses synchronized executable best quotes and a shared-collateral ledger for linked positions. Neither constructs an intrabar path from OHLC.

## Five configurable recipes

| Recipe | Measurement and decision | Linked positions and required evidence |
| --- | --- | --- |
| Volatility Doppelgänger | A measured/model fair-IV comparison between correlated underlyings | Long cheap call+put, short expensive call+put, explicit vega ratios and delta hedges; contract Greeks, quote sizes, margin, borrow, expiry and assignment |
| Funding-Rate Vampire | Announced funding rate plus spot/perpetual basis | Long spot, matched short **linear** perpetual; funding settlement marks/rates/times, collateral, multiplier, liquidation and fees |
| Catastrophe Calendar | Forecast probability minus executable weather-contract price exceeds a buffer | YES contract with payout and official settlement; exact forecast vintage, geography, interval and settlement definition |
| Dividend Exorcist | Executable conversion gap versus discounted strike and dividends | Stock, put and short call; ex-date entitlement, payment, carry, short margin, physical exercise/assignment and fees |
| Correlation Black Hole | Implied index variance versus weighted constituent variance and declared fair correlation | Index/constituent straddles and explicit delta hedge quantities; matched maturities, universe, weights, Greeks, margin and rehedging |

The bundled recipes are **synthetic contract-mechanics fixtures**. They include negative outcomes and cost/cash comparisons, not a history of actual trades. Synthetic European premiums are fixture generators. The dividend fixture separately uses declared physical option expiry events. No fair volatility, correlation, forecast, dividend or profitable relationship is assumed true for client data.

The simplified two-component correlation formula is `(index_iv² - wa²*iva² - wb²*ivb²)/(2*wa*wb*iva*ivb)`. It is a user-defined measurement for the example, not a reproduction of an exchange index. Actual dispersion also has volatility, vega, gamma and rebalancing risks. See [Cboe implied correlation](https://www.cboe.com/us/indices/implied) and [dispersion](https://www.cboe.com/us/indices/dispersion/).

[OCC's parity explanation](https://prd-web.optionseducation.org/advancedconcepts/put-call-parity) discusses carry/dividends and the American exercise distinction. [OCC assignment guidance](https://www.optionseducation.org/referencelibrary/faq/options-assignment) explains that early assignment cannot be known with certainty. The ledger accepts explicit exercise/assignment events or user stress scenarios; it does not forecast their random allocation. [Coinbase's funding mechanism](https://help.coinbase.com/en/derivatives/perpetual-style-futures/funding-rate) distinguishes periodic funding adjustments from other futures P&L. Funding conventions must be supplied for the selected venue. [Kalshi's order-book explanation](https://help.kalshi.com/en/articles/13823828-the-orderbook) describes executable prices and quantities; it is not a fee or settlement specification for every weather contract.

## Client configuration

Keep the normal data mapping and rule/model configuration. Add `portfolio` to `/api/run`:

```json
{
  "currency": "USD",
  "legs": {"SPOT": 2, "PERP": -2},
  "instruments": [
    {"symbol":"SPOT","kind":"spot","multiplier":1,"quantity_step":0.001},
    {"symbol":"PERP","kind":"perpetual","contract_type":"linear","multiplier":1,"allow_short":true,"initial_margin_rate":0.5,"maintenance_margin_rate":0.25}
  ],
  "events": [],
  "participation_rate": 0.1,
  "max_quote_age_ms": 1000,
  "order_ttl_ms": 60000
}
```

Replace `events` with actual history; an empty list is rejected. Alternatively use `content` plus `format:"csv"` or `"ndjson"`, omitting `events`. All instruments need the same quote/collateral currency. Multiple distinct venues cannot silently share cash; a deliberate `cross_venue_collateral_assumption:"pooled_scenario"` is an explicit hypothetical pool, not a simulation of transfers or venue-specific collateral accounts.

`legs` values can be signed fixed quantities or causal expressions over mapped measurements. Model/rule output target weight scales those quantities; zero exits, missing/hold leaves positions. A cash-buy policy is rejected for linked derivatives because it cannot safely infer basket leverage. Quantities are rounded to declared quantity steps. Rounded hedges and partially filled legs may retain risk; mathematical target ratios are not a claim that execution is neutral.

`ExecutionConfig` controls starting cash, default commission/fixed fee, additional slippage and data/order delays. Quotes supply bid/ask spread, so the separate full-spread assumption is unused. Per-instrument overrides include `fee_bps`, `fixed_fee` and `per_unit_fee` (e.g. a declared option fee per contract), minimum notional, quantity step, borrowability and annual borrow-rate scenario. Rates are not automatically a historical fee/borrow archive.

## Event schema

Every event has `timestamp` (timezone-aware economic/source time), `instrument`, `type` and optional nonnegative integer `sequence`. Quotes may have later `available_at` receipt time. Without it, the configured data delay is added to source time. Duplicate same-instrument/type/source-time/sequence is rejected. Provide real sequence information for simultaneous corporate actions; input order breaks otherwise-equal economic-event ties.

| Type | Additional fields and effect |
| --- | --- |
| `quote` | `bid`, `ask`, `bid_size`, `ask_size`; prices in quote currency per underlying unit, sizes in contract/base quantities; availability controls actionable receipt, source time controls staleness |
| `funding` | Linear perpetual only: decimal `rate`, explicit `mark_price`; cash `-held_contracts × multiplier × mark × rate` before same-time new orders |
| `dividend` | Equity/spot: `amount` per underlying unit, optional `pay_at`; entitlement uses signed holdings at the event clock before new orders; receivable/payable is paid at the separate clock |
| `settlement` | Option/binary: official payout `price` per quoted unit; closes the position and books the cash flow; binary payout bounded by declared maximum |
| `exercise` / `assignment` | Option with underlying: positive `quantity` affected contracts; long exercise or short assignment must match held direction/size; strike cash and physical shares exchange, with premium basis transferred |
| `borrow_rate` | Decimal annual `rate`; prospectively changes short-security borrow accrual |
| `margin` | Changes declared `initial_margin_rate`, `maintenance_margin_rate` and/or `short_margin_per_unit` |

Option specifications require call/put `right`, `strike`, `multiplier`, optional `expires_at`, `exercise_style` and `settlement_type` (cash/physical). Physical ITM delivery requires exercise/assignment, not a fictional cash payout. A zero payout can close a worthless physical option. Inverse/quanto contracts are rejected. Short options require an explicit margin amount per contract. Borrowable short equities require explicit permission and borrowing availability.

Funding uses supplied economic payment events, not a forecast of the next payment. Finance/borrow rates accrue simply through actual elapsed time using last-known marks. Missing historical rates should remain an explicit scenario. This is not a broker's portfolio-margin or tax system.

## Fill, mark and collateral behavior

Orders become eligible after completed reference-bar information, declared readiness and delays. Synchronized supplied quotes permit fills within the next reference bar instead of waiting for its next open. Orders fill independently at ask for buys/bid for sells with extra adverse slippage, within supplied size/participation, quantity/minimum rules, fresh-quote and collateral checks. Unchanged-price snapshots preserve hypothetical consumed liquidity. Pending targets may expire or be superseded. No cross-venue atomic basket or hidden liquidity is fabricated.

Cash securities/options exchange full premium/notional. Linear perpetuals exchange realized P&L and fees, with marked unrealized P&L and margin; their notional is not incorrectly debited as a spot purchase. All positions use conservative executable-side marks. Long premium-paid assets are not rehypothecated as collateral. Shorts and perpetuals reserve declared initial/maintenance amounts. A maintenance breach cancels pending risk and attempts liquidation against available observed liquidity; it can remain partial or insolvent. Insolvency is reported, not clamped away.

The benchmark is same-currency cash with the same declared cash-interest assumption. Results separate trading costs, funding, dividends, financing, receipts/payables, positions, margin excess, stale marks and risk events. The spot candle view is hidden for a multi-contract result because one anchor price cannot describe all executions.

## Evidence strength

The active result includes a deterministic paired moving-block bootstrap interval for mean per-bar net return difference when history is sufficient. It preserves paired benchmark times and short-range dependence under the chosen block assumption. It does not fix unrepresentative history, selection bias, multiple strategy searches, missing corporate actions or inaccurate market data. Independently retained forward periods, full point-in-time provenance, stress tests and operational validation remain necessary for a client edge study.

Professional research depends on observable evidence and explicit missing inputs. This version materially extends the old long-only/bar-only boundary, but does not certify an exchange-exact matching engine, stochastic assignment model, unlimited data/framework support, cross-currency collateral engine or future profitability.

Fixed ticket fees default to once per instrument/order, including partial fills. Choose `fixed_fee_policy:"per_fill"` only for that explicit commission scenario; per-unit fees remain proportional to executed contracts. Closed-tranche profit factor allocates both entry and exit commissions, rather than classifying a losing net round trip as a gross winner. This is a leg/tranche statistic, not a whole-basket win rate.
