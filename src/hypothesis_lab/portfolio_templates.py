"""Reviewable linked-contract recipes; bundled prices/forecasts are synthetic checks."""

from __future__ import annotations

import copy
import csv
import io
import json
import math
from datetime import UTC, datetime, timedelta
from typing import Any

_DEFINITIONS: list[dict[str, Any]] = [
    {
        "id": "volatility_doppelganger",
        "title": "Volatility Doppelgänger",
        "description": "Buy the cheaper straddle and sell the relatively expensive correlated straddle, with explicit vega and delta hedge quantities.",
        "requirements": [
            "Synchronized call/put/underlying bid-ask sizes, expiries, multipliers and Greeks",
            "Point-in-time fair-volatility estimates and correlations",
            "Borrow, fees, short-option margin and exercise events",
        ],
        "limitations": [
            "Fair IV and hedge Greeks are measured/model inputs, not automatically true values. Vega and delta neutrality do not remove gamma, jump, basis or assignment risk."
        ],
    },
    {
        "id": "funding_vampire",
        "title": "Funding-Rate Vampire",
        "description": "Hold spot and a matched short linear perpetual when announced funding and basis satisfy your conditions.",
        "requirements": [
            "Spot and perpetual quote history, contract multiplier and basis",
            "Funding settlement timestamps, actual rates and marks, announcement availability",
            "Margin schedule, liquidation rules, transfer/borrow costs and venue-specific collateral",
        ],
        "limitations": [
            "Funding can reverse and legs can fill unequally. This shared-currency scenario does not imply instant cross-venue collateral transfers."
        ],
    },
    {
        "id": "catastrophe_calendar",
        "title": "Catastrophe Calendar",
        "description": "Buy a weather YES contract when a calibrated forecast exceeds its executable market price by the selected buffer.",
        "requirements": [
            "Forecast vintages and probability for the exact location, interval and settlement definition",
            "Contract quote sizes, fee schedule, payout and official settlement",
            "Publication clocks and out-of-sample probability calibration",
        ],
        "limitations": [
            "Forecast probability is not a guaranteed outcome. Local weather measures must match the contract settlement source and cutoff."
        ],
    },
    {
        "id": "dividend_exorcist",
        "title": "Dividend Exorcist",
        "description": "Test stock/call/put conversion mispricing against discounted strike and dividends, including borrow, carry, assignment and entitlement.",
        "requirements": [
            "Same-strike/same-expiry stock and option executable quotes",
            "Declared dividends, ex-date/payment date, rates and borrow availability",
            "American exercise/assignment events or explicit stress scenarios and margin history",
        ],
        "limitations": [
            "European parity alone does not establish American-option arbitrage. Exercise, financing, shortability and legging can consume apparent mispricing."
        ],
    },
    {
        "id": "correlation_black_hole",
        "title": "Correlation Black Hole",
        "description": "Compare weighted constituent and index implied variance; trade the index straddle against constituent straddles with explicit hedge quantities.",
        "requirements": [
            "Synchronized index/constituent option chains, weights and corporate actions",
            "Matched maturities, implied vols, Greeks and a declared fair-correlation forecast",
            "Per-leg liquidity, funding, margin and rehedging costs",
        ],
        "limitations": [
            "The two-component formula is an illustrative variance relation, not an index methodology or guaranteed correlation trade. Actual constituent universe and vega/gamma exposures matter."
        ],
    },
]


def catalogue() -> list[dict]:
    return copy.deepcopy(_DEFINITIONS)


def _option_price(
    s: float, k: float, t: float, vol: float, right: str
) -> tuple[float, float, float]:
    # Synthetic European premium generator for fixture mechanics, never a valuation recommendation.
    if t <= 0:
        return max(s - k, 0) if right == "call" else max(k - s, 0), 1.0 if s > k else 0.0, 0.0
    sigma = vol * math.sqrt(t)
    d1 = (math.log(s / k) + 0.5 * vol * vol * t) / sigma
    d2 = d1 - sigma

    def normal(x):
        return 0.5 * math.erfc(-x / math.sqrt(2))

    call = s * normal(d1) - k * normal(d2)
    price = call if right == "call" else call - s + k
    return (
        max(price, 0.001),
        normal(d1) if right == "call" else normal(d1) - 1,
        s * math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi) * math.sqrt(t),
    )


def template_payload(identity: str) -> dict:
    descriptor = next((item for item in _DEFINITIONS if item["id"] == identity), None)
    if descriptor is None:
        raise ValueError("Choose a known linked-contract template")
    start = datetime(2024, 1, 1, tzinfo=UTC)
    count = 96
    seconds = 3600
    finish = start + timedelta(seconds=count * seconds)

    def stamp(hour: float):
        return (start + timedelta(hours=hour)).isoformat()

    def security(symbol, kind="equity", **kw):
        return {
            "symbol": symbol,
            "kind": kind,
            "currency": "USD",
            "allow_short": True,
            "borrowable": True,
            "borrow_rate_bps": 100,
            "quantity_step": 0.001,
            **kw,
        }

    def option(symbol, underlying, right):
        return security(
            symbol,
            "option",
            right=right,
            strike=100,
            multiplier=100,
            underlying=underlying,
            expires_at=finish.isoformat(),
            short_margin_per_unit=2000,
            initial_margin_rate=1,
            maintenance_margin_rate=0.5,
            per_unit_fee=0.65,
            quantity_step=1,
        )

    legs: dict[str, Any]
    algorithm: dict[str, Any]
    if identity == "funding_vampire":
        specs = [
            security("SPOT", "spot"),
            security(
                "PERP",
                "perpetual",
                multiplier=1,
                initial_margin_rate=0.5,
                maintenance_margin_rate=0.25,
            ),
        ]
        legs = {"SPOT": 2, "PERP": -2}
        algorithm = {
            "entry": 'col("announced_funding_rate") > 0.00005 and abs(col("basis")) < 0.005',
            "exit": 'col("announced_funding_rate") <= 0 or abs(col("basis")) > 0.01',
        }
    elif identity == "catastrophe_calendar":
        specs = [
            security(
                "WEATHER_YES",
                "binary",
                payout=1,
                allow_short=False,
                quantity_step=1,
                per_unit_fee=0.01,
            )
        ]
        legs = {"WEATHER_YES": 100}
        algorithm = {
            "entry": 'col("forecast_probability") - col("market_probability") > 0.08',
            "exit": 'col("forecast_probability") - col("market_probability") < 0.02',
        }
    elif identity == "volatility_doppelganger":
        specs = [security("A"), security("B")] + [
            option(name, under, right)
            for name, under, right in [
                ("A_C", "A", "call"),
                ("A_P", "A", "put"),
                ("B_C", "B", "call"),
                ("B_P", "B", "put"),
            ]
        ]
        legs = {
            "A_C": 'col("vega_b") / maximum(col("vega_a"), 0.000001)',
            "A_P": 'col("vega_b") / maximum(col("vega_a"), 0.000001)',
            "B_C": -1,
            "B_P": -1,
            "A": '-100 * (col("a_call_delta") + col("a_put_delta")) * col("vega_b") / maximum(col("vega_a"), 0.000001)',
            "B": '100 * (col("b_call_delta") + col("b_put_delta"))',
        }
        algorithm = {
            "entry": 'col("iv_a") < col("fair_iv_a") and col("iv_b") > col("fair_iv_b")',
            "exit": 'col("iv_a") >= col("fair_iv_a") or col("iv_b") <= col("fair_iv_b")',
        }
    elif identity == "dividend_exorcist":
        specs = [security("S"), option("CALL", "S", "call"), option("PUT", "S", "put")]
        for item in specs:
            if item["kind"] == "option":
                item["exercise_style"] = "american"
                item["settlement_type"] = "physical"
        legs = {"S": 100, "CALL": -1, "PUT": 1}
        algorithm = {
            "signals": [
                {
                    "name": "parity_gap",
                    "expression": 'col("call_bid") - col("put_ask") - col("stock_ask") + 100 * col("discount_factor") + col("pv_dividends")',
                }
            ],
            "entry": "parity_gap > 0.25",
            "exit": "parity_gap < 0",
        }
    else:
        specs = [security("INDEX"), security("A"), security("B")] + [
            option(name, under, right)
            for name, under, right in [
                ("I_C", "INDEX", "call"),
                ("I_P", "INDEX", "put"),
                ("A_C", "A", "call"),
                ("A_P", "A", "put"),
                ("B_C", "B", "call"),
                ("B_P", "B", "put"),
            ]
        ]
        legs = {
            "I_C": -1,
            "I_P": -1,
            "A_C": 1,
            "A_P": 1,
            "B_C": 1,
            "B_P": 1,
            "INDEX": '100 * (col("index_call_delta") + col("index_put_delta"))',
            "A": '-100 * (col("a_call_delta") + col("a_put_delta"))',
            "B": '-100 * (col("b_call_delta") + col("b_put_delta"))',
        }
        algorithm = {
            "signals": [
                {
                    "name": "implied_correlation",
                    "expression": '(col("index_iv") ** 2 - col("weight_a") ** 2 * col("iv_a") ** 2 - col("weight_b") ** 2 * col("iv_b") ** 2) / (2 * col("weight_a") * col("weight_b") * col("iv_a") * col("iv_b"))',
                }
            ],
            "entry": 'implied_correlation - col("fair_correlation") > 0.1',
            "exit": 'implied_correlation - col("fair_correlation") < 0.05',
        }
    records = []
    events = []
    prices_last = {}
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
    for i in range(count):
        base = 100 + 2 * math.sin(i / 9) + i * 0.01
        a = base
        b = 100 + 1.8 * math.sin(i / 9 + 0.3)
        idx = (a + b) / 2
        prices = {
            "A": a,
            "B": b,
            "INDEX": idx,
            "S": base - (2 if i >= 48 else 0),
            "SPOT": base,
            "PERP": base * (1 + 0.001 * math.cos(i / 11)),
        }
        t = (count - i) / (24 * 365)
        iva = 0.20 + 0.03 * math.sin(i / 13)
        ivb = 0.32 + 0.03 * math.cos(i / 11)
        ivi = 0.32 + 0.05 * math.sin(i / 19)
        measures = {
            "iv_a": iva,
            "iv_b": ivb,
            "index_iv": ivi,
            "fair_iv_a": 0.23,
            "fair_iv_b": 0.29,
            "weight_a": 0.5,
            "weight_b": 0.5,
            "fair_correlation": 0.3,
            "announced_funding_rate": 0.0001 if i < 64 else -0.00005,
            "basis": prices["PERP"] / prices["SPOT"] - 1,
            "forecast_probability": 0.52 + 0.15 * math.sin(i / 12),
            "market_probability": 0.5 + 0.04 * math.cos(i / 8),
            "discount_factor": math.exp(-0.05 * t),
            "pv_dividends": 2 * math.exp(-0.05 * max(0, (48 - i) / (24 * 365))) if i < 48 else 0,
        }
        for under, prefix, vol in [("A", "a", iva), ("B", "b", ivb), ("INDEX", "index", ivi)]:
            for right in ["call", "put"]:
                premium, delta, vega = _option_price(prices[under], 100, t, vol, right)
                measures[prefix + "_" + right + "_delta"] = delta
                if right == "call":
                    measures["vega_" + prefix] = vega
        for contract in specs:
            symbol = contract["symbol"]
            if contract["kind"] == "option":
                vol = (
                    iva
                    if contract["underlying"] == "A"
                    else ivb
                    if contract["underlying"] == "B"
                    else ivi
                    if contract["underlying"] == "INDEX"
                    else 0.25
                )
                underlying = prices[contract["underlying"]]
                price, delta, vega = _option_price(underlying, 100, t, vol, contract["right"])
                if identity == "dividend_exorcist" and symbol == "CALL":
                    price += 1.0
                spread = 0.02
                size = 100
            elif contract["kind"] == "binary":
                price = measures["market_probability"]
                spread = 0.01
                size = 1000
            else:
                price = prices[symbol]
                spread = 0.02
                size = 10000
            bid = max(0, price - spread / 2)
            ask = price + spread / 2
            events.append(
                {
                    "type": "quote",
                    "instrument": symbol,
                    "timestamp": stamp(i + 1 + (0.2 / 3600)),
                    "bid": bid,
                    "ask": ask,
                    "bid_size": size,
                    "ask_size": size,
                    "sequence": i,
                }
            )
            events.append({**events[-1], "timestamp": stamp(i + 1 - (0.2 / 3600))})
            prices_last[symbol] = price
            if symbol == "CALL":
                measures["call_bid"] = bid
            if symbol == "PUT":
                measures["put_ask"] = ask
            if symbol == "S":
                measures["stock_ask"] = ask
        if identity == "funding_vampire" and (i + 1) % 8 == 0:
            events.append(
                {
                    "type": "funding",
                    "instrument": "PERP",
                    "timestamp": stamp(i + 1),
                    "rate": measures["announced_funding_rate"],
                    "mark_price": prices["PERP"],
                    "sequence": i,
                }
            )
        records.append({"observed_at": stamp(i), "available_at": stamp(i + 1), **measures})
        writer.writerow([stamp(i), base, base + 1, base - 1, base + 0.1, 10000])
    if identity == "dividend_exorcist":
        events.append(
            {
                "type": "dividend",
                "instrument": "S",
                "timestamp": stamp(48),
                "pay_at": stamp(72),
                "amount": 2,
                "sequence": 0,
            }
        )
    for contract in specs:
        if contract["kind"] == "option":
            underlying = prices[contract["underlying"]]
            pay = (
                max(underlying - 100, 0)
                if contract["right"] == "call"
                else max(100 - underlying, 0)
            )
            if contract.get("settlement_type") == "physical" and pay > 0:
                events.append(
                    {
                        "type": "assignment" if contract["symbol"] == "CALL" else "exercise",
                        "instrument": contract["symbol"],
                        "timestamp": finish.isoformat(),
                        "quantity": 1,
                        "sequence": count + 1,
                    }
                )
            else:
                events.append(
                    {
                        "type": "settlement",
                        "instrument": contract["symbol"],
                        "timestamp": finish.isoformat(),
                        "price": pay,
                        "sequence": count + 1,
                    }
                )
        elif contract["kind"] == "binary":
            events.append(
                {
                    "type": "settlement",
                    "instrument": contract["symbol"],
                    "timestamp": finish.isoformat(),
                    "price": 0,
                    "sequence": count + 1,
                }
            )
    fields = [key for key in records[0] if key not in {"observed_at", "available_at"}]
    return {
        "name": descriptor["title"] + " · SYNTHETIC contract mechanics",
        "mode": "algorithm",
        "market_csv": output.getvalue(),
        "feature_data": json.dumps(records),
        "feature_format": "json",
        "feature_mapping": {
            "observed_at_column": "observed_at",
            "available_at_column": "available_at",
            "availability_mode": "column",
            "field_columns": fields,
            "max_age_hours": 2,
        },
        "algorithm": {**algorithm, "sizing": "target", "weight": 1},
        "execution": {
            "initial_cash": 100000,
            "fee_bps": 1,
            "slippage_bps": 1,
            "bar_seconds": seconds,
            "periods_per_year": 8760,
            "data_delay_ms": 100,
            "latency_ms": 250,
        },
        "portfolio": {
            "currency": "USD",
            "instruments": specs,
            "events": events,
            "legs": legs,
            "max_quote_age_ms": 5000,
            "participation_rate": 0.25,
            "order_ttl_ms": 60000,
            "cash_interest_rate_bps": 500,
            "cash_borrow_rate_bps": 500,
            "liquidation_fee_bps": 25,
            "data_status": "SYNTHETIC contract mechanics fixture; no historical strategy effectiveness claim",
            "template_id": identity,
        },
        "provenance_note": "All quotes, forecasts, Greeks, funding and settlement are synthetic declared fixtures. Replace with authorized point-in-time inputs before research claims.",
    }
