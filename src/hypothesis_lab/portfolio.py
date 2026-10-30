"""Shared-collateral multi-contract paper ledger using observed executable quotes.

Linear perpetuals, premium-paid securities/options and cash-settled binaries share
one currency. No option prices, margin schedules, assignments or funding are invented.
"""

from __future__ import annotations

import copy
import csv
import io
import json
import math
import statistics
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any

from .data import Bar, timestamp, validate_bars
from .engine import ExecutionConfig, _delay

KINDS = {"spot", "equity", "option", "perpetual", "binary"}


def number(value: Any, name: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return float(value)


def instruments(raw: list[dict], currency: str) -> dict[str, dict]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= 32:
        raise ValueError("Provide 1..32 contract specifications")
    result = {}
    for source in raw:
        item = dict(source)
        symbol = item.get("symbol")
        if not isinstance(symbol, str) or not 1 <= len(symbol) <= 100 or symbol in result:
            raise ValueError("Each contract needs a distinct symbol")
        if item.get("kind") not in KINDS or item.get("currency", currency) != currency:
            raise ValueError(
                "Choose a supported contract kind and one shared quote/collateral currency"
            )
        if item["kind"] == "perpetual" and item.get("contract_type", "linear") != "linear":
            raise ValueError(
                "Only linear perpetual contracts are supported; inverse/quanto need a different settlement adapter"
            )
        item["multiplier"] = number(item.get("multiplier", 1), "Contract multiplier", minimum=1e-12)
        item["quantity_step"] = number(item.get("quantity_step", 0), "Quantity step", minimum=0)
        item["min_notional"] = number(item.get("min_notional", 0), "Minimum notional", minimum=0)
        item["initial_margin_rate"] = number(
            item.get("initial_margin_rate", 1), "Initial margin", minimum=0
        )
        item["maintenance_margin_rate"] = number(
            item.get("maintenance_margin_rate", 0.5), "Maintenance margin", minimum=0
        )
        if item["maintenance_margin_rate"] > item["initial_margin_rate"]:
            raise ValueError("Maintenance margin cannot exceed initial margin")
        for field in (
            "fee_bps",
            "fixed_fee",
            "per_unit_fee",
            "borrow_rate_bps",
            "short_margin_per_unit",
        ):
            if field in item:
                item[field] = number(item[field], field, minimum=0)
        if item.get("fee_bps", 0) >= 10000:
            raise ValueError("Per-instrument trading fees must be below 10000 bps")
        if item.get("kind") == "option":
            if item.get("settlement_type", "cash") not in {"cash", "physical"}:
                raise ValueError("Option settlement type must be cash or physical")
            if item.get("right") not in {"call", "put"}:
                raise ValueError("Option specifications need call/put right")
            item["strike"] = number(item.get("strike"), "Option strike", minimum=0)
            if item.get("exercise_style", "european") not in {"european", "american"}:
                raise ValueError("Exercise style must be european or american")
            if item.get("allow_short") is True and not item.get("short_margin_per_unit", 0):
                raise ValueError(
                    "Short options require an explicit historical/scenario margin per contract"
                )
        if item.get("kind") == "binary":
            item["payout"] = number(item.get("payout", 1), "Binary full payout", minimum=1e-12)
        if item.get("expires_at"):
            item["expires_at"] = timestamp(item["expires_at"]).isoformat()
        result[symbol] = item
    for item in result.values():
        if item.get("underlying") and item["underlying"] not in result:
            raise ValueError("Option underlying must name another supplied contract")
    return result


def read_events(raw: Any, specs: dict[str, dict], format_name: str = "records") -> list[dict]:
    if format_name == "csv":
        if not isinstance(raw, str) or len(raw.encode()) > 10_000_000:
            raise ValueError("Quote/cash-flow CSV must be text under 10 MB")
        reader = csv.DictReader(io.StringIO(raw.lstrip("\ufeff")))
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("Event CSV needs unique headers")
        raw = list(reader)
        numeric = {
            "bid",
            "ask",
            "bid_size",
            "ask_size",
            "rate",
            "mark_price",
            "amount",
            "quantity",
            "price",
            "initial_margin_rate",
            "maintenance_margin_rate",
            "short_margin_per_unit",
        }
        for row in raw:
            for key in list(row):
                if row[key] == "":
                    del row[key]
                elif key in numeric:
                    row[key] = float(row[key])
    elif format_name == "ndjson":
        if not isinstance(raw, str) or len(raw.encode()) > 10_000_000:
            raise ValueError("Event NDJSON must be text under 10 MB")
        raw = [json.loads(line) for line in raw.splitlines() if line.strip()]
    elif format_name != "records":
        raise ValueError("Portfolio event format must be records, csv or ndjson")
    if not isinstance(raw, list) or not 1 <= len(raw) <= 100_000:
        raise ValueError("Provide 1..100,000 quote/cash-flow events")
    result, keys = [], set()
    for index, source in enumerate(raw):
        if not isinstance(source, dict):
            raise ValueError("Each event must be an object")
        item = dict(source)
        symbol = item.get("instrument")
        if symbol not in specs:
            raise ValueError("Event instrument has no contract specification")
        kind = item.get("type")
        if kind not in {
            "quote",
            "funding",
            "dividend",
            "settlement",
            "assignment",
            "exercise",
            "borrow_rate",
            "margin",
        }:
            raise ValueError("Unsupported portfolio event type")
        when = timestamp(item.get("timestamp", ""))
        available = timestamp(item.get("available_at", item.get("timestamp", "")))
        if available < when:
            raise ValueError("Event availability cannot predate its timestamp")
        sequence = item.get("sequence", 0)
        if type(sequence) is not int or sequence < 0:
            raise ValueError("Event sequence must be a nonnegative integer")
        key = (symbol, when, sequence, kind)
        if key in keys:
            raise ValueError("Duplicate event timestamp/type requires a distinct sequence")
        keys.add(key)
        item.update(
            timestamp=when,
            available_at=available,
            sequence=sequence,
            source_index=index,
            availability_explicit="available_at" in source,
        )
        if kind == "quote":
            for name in ("bid", "ask", "bid_size", "ask_size"):
                item[name] = number(item.get(name), name, minimum=0)
            if item["bid"] > item["ask"] or item["ask"] <= 0:
                raise ValueError("Quotes must be uncrossed with a positive ask")
            if specs[symbol]["kind"] == "binary" and item["ask"] > specs[symbol]["payout"]:
                raise ValueError("Binary quote exceeds its contract payout")
        elif kind == "funding":
            if specs[symbol]["kind"] != "perpetual":
                raise ValueError("Funding events require a linear perpetual")
            item["rate"] = number(item.get("rate"), "Funding decimal rate")
            item["mark_price"] = number(item.get("mark_price"), "Funding mark", minimum=1e-12)
        elif kind == "dividend":
            if specs[symbol]["kind"] not in {"equity", "spot"}:
                raise ValueError("Dividends require a cash security")
            item["amount"] = number(item.get("amount"), "Dividend per underlying unit", minimum=0)
            item["pay_at"] = timestamp(item.get("pay_at", item["timestamp"]))
            if item["pay_at"] < when:
                raise ValueError("Dividend pay time cannot precede entitlement time")
        elif kind == "settlement":
            if specs[symbol]["kind"] not in {"option", "binary"}:
                raise ValueError("Cash settlement requires an option or binary contract")
            item["price"] = number(
                item.get("price"), "Official settlement per quoted unit", minimum=0
            )
            if (
                specs[symbol]["kind"] == "option"
                and specs[symbol].get("settlement_type", "cash") == "physical"
                and item["price"] != 0
            ):
                raise ValueError(
                    "Physical options need exercise/assignment delivery; only worthless expiry can cash settle at zero"
                )
            if specs[symbol]["kind"] == "binary" and item["price"] > specs[symbol]["payout"]:
                raise ValueError("Binary settlement exceeds its payout")
        elif kind in {"assignment", "exercise"}:
            if specs[symbol]["kind"] != "option" or not specs[symbol].get("underlying"):
                raise ValueError(
                    "Physical exercise/assignment needs option and underlying specifications"
                )
            if specs[specs[symbol]["underlying"]]["kind"] not in {"equity", "spot"}:
                raise ValueError("Physical delivery currently requires a spot/equity underlying")
            if specs[symbol].get("settlement_type", "cash") != "physical":
                raise ValueError("Cash-settled options cannot deliver physical shares")
            if specs[symbol].get("exercise_style", "european") == "european":
                if not specs[symbol].get("expires_at") or when < timestamp(
                    specs[symbol]["expires_at"]
                ):
                    raise ValueError(
                        "European exercise/assignment requires its declared expiration time"
                    )
            item["quantity"] = number(item.get("quantity"), "Exercised contracts", minimum=1e-12)
        elif kind == "borrow_rate":
            item["rate"] = number(item.get("rate"), "Annual borrow decimal rate", minimum=0)
        else:
            for name in ("initial_margin_rate", "maintenance_margin_rate", "short_margin_per_unit"):
                if name in item:
                    item[name] = number(item[name], name, minimum=0)
        result.append(item)
    return result


def portfolio_backtest(
    bars: list[Bar],
    targets: list[dict | None],
    config: ExecutionConfig,
    specification: dict,
    *,
    start_index: int = 0,
    end_index: int | None = None,
) -> dict:
    """Target signed contract quantities; independent legs expose actual legging risk."""
    validate_bars(bars)
    cfg = config
    end = len(bars) if end_index is None else end_index
    if (
        len(targets) != len(bars)
        or not 0 <= start_index < end <= len(bars)
        or end - start_index < 2
    ):
        raise ValueError(
            "Portfolio targets and evaluation bounds must match at least two reference bars"
        )
    if any(
        (b.timestamp - a.timestamp).total_seconds() < cfg.bar_seconds
        for a, b in zip(bars, bars[1:])
    ):
        raise ValueError("Reference bars overlap their configured duration")
    currency = specification.get("currency", "USD")
    if not isinstance(currency, str) or not currency or len(currency) > 12:
        raise ValueError("Choose a collateral currency")
    specs = instruments(specification.get("instruments", []), currency)
    venues = {item.get("venue", "default") for item in specs.values()}
    if (
        len(venues) > 1
        and specification.get("cross_venue_collateral_assumption") != "pooled_scenario"
    ):
        raise ValueError(
            "Distinct venues cannot silently share collateral; use one funded venue or explicitly declare a pooled_scenario"
        )
    events = read_events(
        specification.get("events", specification.get("content")),
        specs,
        specification.get("format", "records"),
    )
    participation = number(
        specification.get("participation_rate", 0.1), "Displayed size participation", minimum=1e-12
    )
    if participation > 1:
        raise ValueError("Participation cannot exceed observed displayed size")
    max_age = number(specification.get("max_quote_age_ms", 1000), "Maximum quote age", minimum=0)
    fixed_policy = specification.get("fixed_fee_policy", "per_order")
    if fixed_policy not in {"per_order", "per_fill"}:
        raise ValueError("Fixed fee policy must be per_order or per_fill")
    ttl = number(specification.get("order_ttl_ms", 60000), "Target-order TTL", minimum=1e-12)
    loan_rate = (
        number(specification.get("cash_borrow_rate_bps", 0), "Cash loan interest", minimum=0)
        / 10000
    )
    cash_rate = (
        number(specification.get("cash_interest_rate_bps", 0), "Cash interest", minimum=0) / 10000
    )
    liquidation_fee = (
        number(specification.get("liquidation_fee_bps", 0), "Liquidation surcharge", minimum=0)
        / 10000
    )
    if loan_rate > 10 or cash_rate > 10 or liquidation_fee >= 1:
        raise ValueError("Financing/liquidation rates exceed supported bounds")
    start = bars[start_index].timestamp
    finish = bars[end - 1].timestamp + timedelta(seconds=cfg.bar_seconds)
    positions = {
        symbol: {
            "units": 0.0,
            "average_entry": 0.0,
            "realized_pnl": 0.0,
            "entry_fees_remaining": 0.0,
        }
        for symbol in specs
    }
    books: dict[str, dict] = {}
    cash = cfg.initial_cash
    dividends_receivable = 0.0
    fills = []
    cashflows = []
    orders: list[dict[str, Any]] = []
    equity = []
    risk_events = []
    closed = []
    settled = set()
    pending: list[dict[str, Any]] = []
    timeline: list[tuple[datetime, int, int, int, str, Any]] = []
    order_counter = 0
    paid = 0.0
    realized = 0.0
    entitlements = {}
    # Quotes are actionable on receipt. Economic cash flows use settlement/entitlement time;
    # their availability is never used as a predictive signal by this ledger.
    for event in events:
        clock = (
            (
                event["available_at"]
                if event["availability_explicit"]
                else event["timestamp"] + _delay(cfg.data_delay_ms)
            )
            if event["type"] == "quote"
            else event["timestamp"]
        )
        if clock <= finish:
            timeline.append(
                (
                    clock,
                    0 if event["type"] != "quote" else 1,
                    event["sequence"],
                    event["source_index"],
                    "event",
                    event,
                )
            )
            if event["type"] == "dividend" and event["pay_at"] <= finish:
                timeline.append(
                    (
                        event["pay_at"],
                        0,
                        event["sequence"],
                        event["source_index"],
                        "dividend_payment",
                        event,
                    )
                )
    for index in range(start_index, end):
        intent = targets[index]
        if intent is not None:
            if (
                not isinstance(intent, dict)
                or not isinstance(intent.get("targets"), dict)
                or set(intent["targets"]) - set(specs)
            ):
                raise ValueError(
                    "Portfolio intent needs a targets object naming supplied instruments"
                )
            desired = {
                symbol: number(value, "Target signed quantity")
                for symbol, value in intent["targets"].items()
            }
            ready = (
                bars[index].timestamp
                + timedelta(seconds=cfg.bar_seconds)
                + _delay(cfg.data_delay_ms)
            )
            if intent.get("available_at"):
                ready = max(ready, timestamp(intent["available_at"]))
            eligible = ready + _delay(cfg.latency_ms)
            limits = intent.get("limits", {})
            if not isinstance(limits, dict) or set(limits) - set(specs):
                raise ValueError("Limit prices must name supplied instruments")
            for value in limits.values():
                number(value, "Limit price", minimum=0)
            order: dict[str, Any] = {
                "id": f"basket-{index}",
                "targets": desired,
                "limits": limits,
                "submitted_bar": index,
                "decision_bar_open": bars[index].timestamp.isoformat(),
                "decision_at": ready.isoformat(),
                "eligible_at": eligible.isoformat(),
                "expires_at": eligible + timedelta(milliseconds=ttl),
                "status": "pending",
                "rejections": [],
                "requested_targets": dict(desired),
            }
            timeline.append((eligible, 2, 0, index, "intent", order))
        timeline.append(
            (
                bars[index].timestamp + timedelta(seconds=cfg.bar_seconds),
                4,
                0,
                index,
                "value",
                index,
            )
        )
    timeline.sort(key=lambda item: item[:4])
    previous_clock = start
    liquidating = False
    financing_rates = {
        symbol: spec.get("borrow_rate_bps", 0) / 10000 for symbol, spec in specs.items()
    }

    def mark(symbol: str, q: float | None = None) -> float:
        held = positions[symbol]["units"] if q is None else q
        book = books.get(symbol)
        if book is None:
            if held:
                raise ValueError(f"No quote exists to value open contract {symbol}")
            return 0.0
        return book["bid"] if held >= 0 else book["ask"]

    def snapshot() -> tuple[float, float, float, float]:
        value = 0.0
        long_security = 0.0
        initial = maintenance = 0.0
        for symbol, state in positions.items():
            q = state["units"]
            spec = specs[symbol]
            price = mark(symbol)
            mult = spec["multiplier"]
            if spec["kind"] == "perpetual":
                value += q * mult * (price - state["average_entry"])
            else:
                value += q * mult * price
                long_security += max(q, 0) * mult * price
            if spec["kind"] == "perpetual" or q < 0:
                if spec["kind"] == "option" and q < 0:
                    initial += abs(q) * spec.get("short_margin_per_unit", 0)
                    maintenance += (
                        abs(q)
                        * spec.get("short_margin_per_unit", 0)
                        * spec["maintenance_margin_rate"]
                        / max(spec["initial_margin_rate"], 1e-12)
                    )
                elif spec["kind"] == "binary" and q < 0:
                    margin = abs(q) * mult * (spec["payout"] - price)
                    initial += margin
                    maintenance += margin
                else:
                    initial += abs(q) * mult * price * spec["initial_margin_rate"]
                    maintenance += abs(q) * mult * price * spec["maintenance_margin_rate"]
        account = cash + dividends_receivable + value
        # Long premium-paid assets are not rehypothecated as margin collateral.
        collateral = account - long_security - dividends_receivable
        return account, collateral - initial, collateral - maintenance, value

    def apply_fill(
        symbol: str, delta: float, price: float, fee: float, fee_basis_extra: float = 0
    ) -> float:
        nonlocal cash, realized
        state = positions[symbol]
        spec = specs[symbol]
        old = state["units"]
        avg = state["average_entry"]
        mult = spec["multiplier"]
        closed_units = min(abs(old), abs(delta)) if old * delta < 0 else 0.0
        gain = closed_units * (price - avg) * (1 if old > 0 else -1) * mult
        entry_allocated = state["entry_fees_remaining"] * closed_units / abs(old) if old else 0.0
        closing_fee = (fee + fee_basis_extra) * closed_units / abs(delta) if delta else 0.0
        if closed_units:
            closed.append(gain - entry_allocated - closing_fee)
        opened = abs(delta) - closed_units
        state["entry_fees_remaining"] -= entry_allocated
        if delta:
            state["entry_fees_remaining"] += (fee + fee_basis_extra) * opened / abs(delta)
        if spec["kind"] == "perpetual":
            cash += gain - fee
        else:
            cash -= delta * price * mult + fee
        new = old + delta
        if abs(new) < 1e-12:
            new = 0.0
        if old * delta >= 0 and new:
            state["average_entry"] = (abs(old) * avg + abs(delta) * price) / abs(new)
        elif old * new < 0:
            state["average_entry"] = price
        elif not new:
            state["average_entry"] = 0.0
        state["units"] = new
        state["realized_pnl"] += gain - fee
        realized += gain - fee
        return gain

    def reject_order(order: dict, symbol: str, reason: str, now) -> None:
        for previous in order["rejections"]:
            if previous["instrument"] == symbol and previous["reason"] == reason:
                previous["attempts"] = previous.get("attempts", 1) + 1
                previous["last_at"] = now.isoformat()
                return
        if len(order["rejections"]) < 128:
            order["rejections"].append(
                {
                    "instrument": symbol,
                    "at": now.isoformat(),
                    "last_at": now.isoformat(),
                    "attempts": 1,
                    "reason": reason,
                }
            )

    def execute(order: dict, now) -> None:
        nonlocal paid, cash, realized
        if now >= order["expires_at"]:
            order["status"] = "expired"
            return
        any_remaining = False
        for symbol, target in order["targets"].items():
            state = positions[symbol]
            spec = specs[symbol]
            delta = target - state["units"]
            if abs(delta) < 1e-10:
                continue
            any_remaining = True
            if symbol in settled or (
                spec.get("expires_at") and now >= timestamp(spec["expires_at"])
            ):
                reject_order(order, symbol, "contract_expired_or_settled", now)
                continue
            book = books.get(symbol)
            if book is None or (now - book["timestamp"]).total_seconds() * 1000 > max_age:
                continue
            side = "buy" if delta > 0 else "sell"
            key = "ask" if delta > 0 else "bid"
            reference = book[key]
            if reference <= 0:
                continue
            price = reference * (1 + (cfg.slippage_bps / 10000) * (1 if delta > 0 else -1))
            if symbol in order["limits"] and (
                price > order["limits"][symbol] if delta > 0 else price < order["limits"][symbol]
            ):
                continue
            quantity = min(abs(delta), book[key + "_remaining"])
            step = spec["quantity_step"]
            if step:
                quantity = math.floor((quantity + step * 1e-12) / step) * step
            if quantity <= 0 or quantity * price * spec["multiplier"] < spec["min_notional"]:
                continue
            actual = quantity * (1 if delta > 0 else -1)
            new = state["units"] + actual
            risk_reducing = abs(new) <= abs(state["units"]) and state["units"] * new >= 0
            if new < 0 and (
                spec.get("allow_short") is not True
                or (spec["kind"] in {"spot", "equity"} and spec.get("borrowable") is not True)
            ):
                reject_order(order, symbol, "short_or_borrow_not_authorized", now)
                continue
            fee_rate = spec.get("fee_bps", cfg.fee_bps) / 10000 + (
                liquidation_fee if order.get("liquidation") else 0
            )
            fixed = (
                spec.get("fixed_fee", cfg.fixed_fee)
                if fixed_policy == "per_fill"
                or symbol not in order.get("commission_charged_instruments", [])
                else 0.0
            )
            ticket_fee = fixed + quantity * spec.get("per_unit_fee", 0)
            fee = quantity * price * spec["multiplier"] * fee_rate + ticket_fee
            before_cash = cash
            before = state.copy()
            before_realized = realized
            before_closed_count = len(closed)
            gain = apply_fill(symbol, actual, price, fee)
            _, available, _, _ = snapshot()
            if not risk_reducing and (available < -1e-8 or liquidating):
                cash = before_cash
                positions[symbol] = before
                realized = before_realized
                del closed[before_closed_count:]
                reject_order(order, symbol, "insufficient_initial_collateral", now)
                continue
            book[key + "_remaining"] -= quantity
            paid += fee
            if symbol not in order.setdefault("commission_charged_instruments", []):
                order["commission_charged_instruments"].append(symbol)
            fills.append(
                {
                    "instrument": symbol,
                    "contract_kind": spec["kind"],
                    "side": side,
                    "units": quantity,
                    "quantity": quantity,
                    "signed_units": actual,
                    "multiplier": spec["multiplier"],
                    "price": price,
                    "reference_price": reference,
                    "notional": quantity * price * spec["multiplier"],
                    "fee": fee,
                    "proportional_fee": quantity * price * spec["multiplier"] * fee_rate,
                    "fixed_fee": ticket_fee,
                    "spread_cost": quantity * spec["multiplier"] * (book["ask"] - book["bid"]) / 2,
                    "slippage_cost": quantity * spec["multiplier"] * abs(price - reference),
                    "realized_pnl": gain - fee,
                    "cash_after": cash,
                    "units_after": positions[symbol]["units"],
                    "decision_bar_open": order["decision_bar_open"],
                    "decision_at": order["decision_at"],
                    "eligible_at": order["eligible_at"],
                    "filled_at": now.isoformat(),
                    "timestamp": now.isoformat(),
                    "order_id": order["id"],
                    "partial": abs(target - positions[symbol]["units"]) > 1e-10,
                    "liquidation": bool(order.get("liquidation")),
                }
            )
        order["status"] = (
            "filled"
            if all(
                abs(target - positions[symbol]["units"]) < 1e-10
                for symbol, target in order["targets"].items()
            )
            else "pending"
            if any_remaining
            else "no_change"
        )

    for now, priority, sequence, index, action, item in timeline:
        if now < start:
            if action == "event" and item["type"] == "quote":
                books[item["instrument"]] = {
                    **item,
                    "bid_remaining": item["bid_size"] * participation,
                    "ask_remaining": item["ask_size"] * participation,
                }
            elif action == "event" and item["type"] == "borrow_rate":
                financing_rates[item["instrument"]] = item["rate"]
            elif action == "event" and item["type"] == "margin":
                spec = specs[item["instrument"]]
                for name in (
                    "initial_margin_rate",
                    "maintenance_margin_rate",
                    "short_margin_per_unit",
                ):
                    if name in item:
                        spec[name] = item[name]
                if spec["maintenance_margin_rate"] > spec["initial_margin_rate"]:
                    raise ValueError("Historical maintenance margin exceeds initial margin")
            elif action == "event" and item["type"] == "settlement":
                settled.add(item["instrument"])
            continue
        if now > finish:
            continue
        elapsed = max(0, (now - previous_clock).total_seconds()) / (365 * 86400)
        if elapsed:
            interest = (max(cash, 0) * cash_rate - max(-cash, 0) * loan_rate) * elapsed
            borrow = (
                -sum(
                    max(-state["units"], 0)
                    * mark(symbol)
                    * specs[symbol]["multiplier"]
                    * financing_rates[symbol]
                    for symbol, state in positions.items()
                    if specs[symbol]["kind"] in {"equity", "spot"}
                )
                * elapsed
            )
            cash += interest + borrow
            if interest or borrow:
                cashflows.append(
                    {
                        "type": "financing",
                        "timestamp": now.isoformat(),
                        "cash": interest + borrow,
                        "interest": interest,
                        "borrow": borrow,
                    }
                )
        previous_clock = now
        if action == "event":
            symbol = item["instrument"]
            spec = specs[symbol]
            state = positions[symbol]
            kind = item["type"]
            if kind == "quote":
                old = books.get(symbol)
                if old is not None and item["timestamp"] < old["timestamp"]:
                    risk_events.append(
                        {
                            "type": "ignored_out_of_order_quote",
                            "instrument": symbol,
                            "timestamp": now.isoformat(),
                        }
                    )
                    continue
                book = dict(item)
                for side in ("bid", "ask"):
                    size = item[side + "_size"] * participation
                    book[side + "_remaining"] = (
                        size
                        if old is None or old[side] != item[side]
                        else max(
                            0,
                            min(
                                size,
                                old[side + "_remaining"]
                                + (item[side + "_size"] - old[side + "_size"]) * participation,
                            ),
                        )
                    )
                books[symbol] = book
            elif kind == "funding":
                value = -state["units"] * spec["multiplier"] * item["mark_price"] * item["rate"]
                cash += value
                cashflows.append(
                    {
                        "type": kind,
                        "instrument": symbol,
                        "timestamp": now.isoformat(),
                        "cash": value,
                        "held_units": state["units"],
                        "rate": item["rate"],
                    }
                )
            elif kind == "dividend":
                value = state["units"] * spec["multiplier"] * item["amount"]
                dividends_receivable += value
                # Entitlement is captured before same-time orders; payment is a separate clock.
                cashflows.append(
                    {
                        "type": "dividend_entitlement",
                        "instrument": symbol,
                        "timestamp": now.isoformat(),
                        "cash": 0,
                        "receivable": value,
                        "pay_at": item["pay_at"].isoformat(),
                        "held_units": state["units"],
                    }
                )
                entitlements[item["source_index"]] = value
            elif kind == "settlement":
                gain = (
                    state["units"] * spec["multiplier"] * (item["price"] - state["average_entry"])
                )
                realized += gain
                state["realized_pnl"] += gain
                if state["units"]:
                    closed.append(gain - state["entry_fees_remaining"])
                state["entry_fees_remaining"] = 0.0
                value = state["units"] * spec["multiplier"] * item["price"]
                cash += value
                state["units"] = 0
                state["average_entry"] = 0
                settled.add(symbol)
                cashflows.append(
                    {
                        "type": kind,
                        "instrument": symbol,
                        "timestamp": now.isoformat(),
                        "cash": value,
                        "settlement_price": item["price"],
                    }
                )
                for order in pending:
                    order["targets"].pop(symbol, None)
            elif kind in {"assignment", "exercise"}:
                q = state["units"]
                if not q:
                    risk_events.append(
                        {
                            "type": "position_event_not_applicable",
                            "instrument": symbol,
                            "event": kind,
                            "timestamp": now.isoformat(),
                        }
                    )
                    continue
                quantity = item["quantity"]
                if (
                    quantity > abs(q) + 1e-10
                    or (kind == "assignment" and q >= 0)
                    or (kind == "exercise" and q <= 0)
                ):
                    raise ValueError(
                        "Exercise/assignment quantity and direction must match the held option position"
                    )
                underlying = spec["underlying"]
                under = specs[underlying]
                sign = 1 if q > 0 else -1
                delivered = (
                    sign
                    * (1 if spec["right"] == "call" else -1)
                    * quantity
                    * spec["multiplier"]
                    / under["multiplier"]
                )
                transfer_fee = state["entry_fees_remaining"] * quantity / abs(q)
                state["entry_fees_remaining"] -= transfer_fee
                premium = state["average_entry"]
                old_under = positions[underlying].copy()
                state["units"] -= sign * quantity
                if not state["units"]:
                    state["average_entry"] = 0
                apply_fill(underlying, delivered, spec["strike"], 0, transfer_fee)
                # Transfer the option premium basis into delivered/received shares;
                # strike cash remains actual, and no premium is charged twice.
                effective = spec["strike"] + (premium if spec["right"] == "call" else -premium)
                under_state = positions[underlying]
                old_q = old_under["units"]
                new_q = under_state["units"]
                if old_q * delivered >= 0 and new_q:
                    under_state["average_entry"] = (
                        abs(old_q) * old_under["average_entry"] + abs(delivered) * effective
                    ) / abs(new_q)
                elif old_q * delivered < 0:
                    closed_q = min(abs(old_q), abs(delivered))
                    adjustment = (
                        closed_q
                        * (effective - spec["strike"])
                        * (1 if old_q > 0 else -1)
                        * under["multiplier"]
                    )
                    under_state["realized_pnl"] += adjustment
                    realized += adjustment
                    if closed_q:
                        closed[-1] += adjustment
                    if old_q * new_q < 0:
                        under_state["average_entry"] = effective
                cashflows.append(
                    {
                        "type": kind,
                        "instrument": symbol,
                        "underlying": underlying,
                        "timestamp": now.isoformat(),
                        "cash": -delivered * under["multiplier"] * spec["strike"],
                        "delivered_units": delivered,
                        "contracts": quantity,
                    }
                )
            elif kind == "borrow_rate":
                financing_rates[symbol] = item["rate"]
            else:
                for name in (
                    "initial_margin_rate",
                    "maintenance_margin_rate",
                    "short_margin_per_unit",
                ):
                    if name in item:
                        spec[name] = item[name]
                if spec["maintenance_margin_rate"] > spec["initial_margin_rate"]:
                    raise ValueError("Updated maintenance margin exceeds initial margin")
        elif action == "intent":
            if liquidating:
                item["status"] = "rejected_liquidation_in_progress"
                orders.append(item)
            else:
                # A fresh target replaces outstanding targets for the same symbols, not fills already made.
                for old in pending:
                    for symbol in item["targets"]:
                        old["targets"].pop(symbol, None)
                    if not old["targets"]:
                        old["status"] = "superseded"
                pending.append(item)
                orders.append(item)
        elif action == "dividend_payment":
            value = entitlements.pop(item["source_index"], 0.0)
            cash += value
            dividends_receivable -= value
            cashflows.append(
                {
                    "type": "dividend_payment",
                    "instrument": item["instrument"],
                    "timestamp": now.isoformat(),
                    "cash": value,
                }
            )
        pending = [order for order in pending if order["status"] == "pending"]
        for order in pending:
            if order["status"] == "pending":
                execute(order, now)
        account, available, maintenance, value = snapshot()
        if maintenance < -1e-8 and not liquidating:
            liquidating = True
            risk_events.append(
                {
                    "type": "maintenance_margin_breach",
                    "timestamp": now.isoformat(),
                    "equity": account,
                    "maintenance_excess": maintenance,
                }
            )
            for order in pending:
                if order["status"] == "pending":
                    order["status"] = "cancelled_margin_breach"
            order_counter += 1
            liquidate = {
                "id": f"liquidation-{order_counter}",
                "targets": {symbol: 0.0 for symbol in positions},
                "limits": {},
                "decision_bar_open": now.isoformat(),
                "decision_at": now.isoformat(),
                "eligible_at": now.isoformat(),
                "expires_at": finish + timedelta(seconds=1),
                "status": "pending",
                "rejections": [],
                "liquidation": True,
            }
            pending.append(liquidate)
            orders.append(liquidate)
            execute(liquidate, now)
            account, available, maintenance, value = snapshot()
        if not all(math.isfinite(v) for v in (cash, account, available, maintenance, value)):
            raise ValueError("Portfolio arithmetic exceeds finite limits")
        if action == "value":
            equity.append(
                {
                    "timestamp": bars[item].timestamp.isoformat(),
                    "valuation_at": now.isoformat(),
                    "equity": account,
                    "cash": cash,
                    "dividends_receivable": dividends_receivable,
                    "position_value": value,
                    "units": 0,
                    "average_cost": None,
                    "realized_pnl": realized,
                    "unrealized_pnl": account
                    - cfg.initial_cash
                    - realized
                    - sum(
                        f["cash"]
                        for f in cashflows
                        if f["type"] not in {"assignment", "exercise", "settlement"}
                    ),
                    "initial_margin_excess": available,
                    "maintenance_margin_excess": maintenance,
                    "positions": copy.deepcopy(positions),
                    "mark_prices": {symbol: mark(symbol) for symbol in specs},
                    "stale_marks": [
                        symbol
                        for symbol, state in positions.items()
                        if state["units"]
                        and (now - books[symbol]["timestamp"]).total_seconds() * 1000 > max_age
                    ],
                }
            )
    for order in pending:
        if order["status"] == "pending":
            order["status"] = "expired_end_of_data"
        order["expires_at"] = order["expires_at"].isoformat()
    # Superseded/filled orders also retain an exportable expiry clock.
    for order in orders:
        if not isinstance(order["expires_at"], str):
            order["expires_at"] = order["expires_at"].isoformat()
    peak = cfg.initial_cash
    for row in equity:
        peak = max(peak, row["equity"])
        row["drawdown"] = row["equity"] / peak - 1
    values = [row["equity"] for row in equity]
    returns = [b / a - 1 for a, b in zip([cfg.initial_cash] + values[:-1], values) if a > 0]
    vol = statistics.stdev(returns) if len(returns) > 1 and min(values) > 0 else None
    metrics = {
        "total_return": values[-1] / cfg.initial_cash - 1,
        "final_equity": values[-1],
        "max_drawdown": min(row["drawdown"] for row in equity),
        "annualized_return": None,
        "annualized_volatility": vol * math.sqrt(cfg.periods_per_year) if vol is not None else None,
        "sharpe": statistics.mean(returns) / vol * math.sqrt(cfg.periods_per_year)
        if vol and (finish - start).total_seconds() >= 30 * 86400
        else None,
        "trade_count": len(fills),
        "closed_trade_count": len(closed),
        "profit_factor": sum(max(p, 0) for p in closed) / (-sum(min(p, 0) for p in closed))
        if any(p < 0 for p in closed)
        else None,
        "turnover": sum(f["notional"] for f in fills) / cfg.initial_cash,
        "fees_paid": paid,
        "proportional_fees_paid": sum(f["proportional_fee"] for f in fills),
        "fixed_fees_paid": sum(f["fixed_fee"] for f in fills),
        "spread_cost": sum(f["spread_cost"] for f in fills),
        "slippage_cost": sum(f["slippage_cost"] for f in fills),
        "funding_cash": sum(f["cash"] for f in cashflows if f["type"] == "funding"),
        "dividend_cash": sum(f["cash"] for f in cashflows if f["type"] == "dividend_payment"),
        "financing_cash": sum(f["cash"] for f in cashflows if f["type"] == "financing"),
        "margin_calls": sum(event["type"] == "maintenance_margin_breach" for event in risk_events),
    }
    coverage = {
        "quotes": sum(e["type"] == "quote" for e in events),
        "funding_events": sum(e["type"] == "funding" for e in events),
        "cashflow_events": len(cashflows),
        "instruments": len(specs),
        "stale_valuation_rows": sum(bool(row["stale_marks"]) for row in equity),
        "unsettled_expired_contracts": [
            symbol
            for symbol, spec in specs.items()
            if spec.get("expires_at")
            and timestamp(spec["expires_at"]) <= finish
            and symbol not in settled
            and positions[symbol]["units"]
        ],
    }
    return {
        "metrics": metrics,
        "equity": equity,
        "fills": fills,
        "orders": orders,
        "order_events": orders,
        "cashflows": cashflows,
        "net_closed_tranche_pnls": closed,
        "risk_events": risk_events,
        "configuration": asdict(cfg),
        "portfolio": {
            "currency": currency,
            "instruments": list(specs.values()),
            "coverage": coverage,
            "final_positions": positions,
            "metric_scope": "Closed-tranche profit factor includes allocated entry and exit commissions; it is not a whole-basket trade statistic",
            "execution": "Observed best-quote, independent legs, shared collateral",
        },
        "warnings": [
            "Prices and displayed sizes come from supplied quotes; no intrabar OHLC path or option pricing is fabricated. Partial legs and unhedged exposure are possible. Displayed liquidity is depleted and unchanged-price snapshots preserve shadow consumption.",
            "This shared-currency ledger supports signed spot/equity, premium-paid options, linear perpetuals and binary contracts. Margin/borrow/fee schedules and assignment/settlement events must be supplied; rates are scenarios, not a broker risk engine. American assignment is replayed only when explicitly supplied.",
            "Financing uses simple time accrual on last-known marks with supplied annual rates. Funding uses supplied settlement marks/rates and held contracts before same-time orders. Dividend entitlement and payment are separate. No FX, portfolio-margin offsets, stochastic assignment or cross-venue atomic fill is inferred.",
            "Liquidation attempts use available displayed quotes and can remain partial or insolvent. Stale marks remain flagged; missing settlement or financing history weakens evidence. Positive results are conditional on these data and assumptions.",
        ],
    }
