"""Optional observed quote/trade replay with explicit, conservative L2 assumptions.

This is a single-venue, single-instrument spot paper replay, not a reconstructed
matching engine. Full-depth records are absolute snapshots, never raw deltas.
"""

from __future__ import annotations

import bisect
import csv
import heapq
import io
import json
import math
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_FLOOR, Decimal
from typing import Any

from .data import Bar, timestamp, validate_bars
from .engine import Decision, ExecutionConfig, calculate_metrics

MAX_RECORDS = 100_000
MAX_TEXT_BYTES = 16_000_000


def _number(value: Any, name: str, *, minimum: float = 0, positive: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{name} must be a finite number") from None
    if not math.isfinite(result) or result < minimum or (positive and result <= 0):
        raise ValueError(f"{name} is outside its finite supported range")
    return result


def _milliseconds(value: float) -> timedelta:
    return timedelta(microseconds=math.ceil(value * 1000))


@dataclass(frozen=True)
class ReplayConfig:
    instrument: str
    max_quote_age_ms: float = 1000
    participation_rate: float = 0.1
    quantity_step: float = 0
    min_notional: float = 0
    limit_ttl_ms: float = 60_000
    queue_ahead_multiplier: float = 1
    maker_fee_bps: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,63}", self.instrument
        ):
            raise ValueError("Choose one exact instrument key, such as BTC/USD")
        for name in (
            "max_quote_age_ms",
            "participation_rate",
            "quantity_step",
            "min_notional",
            "limit_ttl_ms",
            "queue_ahead_multiplier",
        ):
            object.__setattr__(self, name, _number(getattr(self, name), name))
        if not 0 < self.participation_rate <= 1:
            raise ValueError("Participation must be greater than zero and at most one")
        if (
            not 0 < self.max_quote_age_ms <= 86_400_000
            or not 0 < self.limit_ttl_ms <= 31_536_000_000
        ):
            raise ValueError(
                "Quote age must be positive and <=1 day; limit TTL positive and <=365 days"
            )
        if not 0 <= self.queue_ahead_multiplier <= 10:
            raise ValueError("Queue-ahead multiplier must be 0..10; it is an explicit assumption")
        if (
            self.maker_fee_bps is not None
            and not 0 <= _number(self.maker_fee_bps, "maker fee") < 10_000
        ):
            raise ValueError("Maker fee must be 0..10000 bps, excluding rebates")
        if self.maker_fee_bps is not None:
            object.__setattr__(self, "maker_fee_bps", float(self.maker_fee_bps))


def _levels(value: Any, name: str) -> list[list[float]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            raise ValueError(f"{name} must be a JSON array of [price, base quantity]") from None
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError("Each absolute depth side needs at most 100 displayed levels")
    result = []
    for level in value:
        if not isinstance(level, (list, tuple)) or len(level) != 2:
            raise ValueError("Each depth level is [quote price per base unit, base quantity]")
        result.append(
            [_number(level[0], "level price", positive=True), _number(level[1], "level quantity")]
        )
    if len({level[0] for level in result}) != len(result):
        raise ValueError("Duplicate depth price levels are ambiguous")
    return sorted(result, reverse=name == "bids")


def parse_replay(
    source: str | list[dict], format: str = "records", *, instrument: str
) -> list[dict]:
    """Normalize bounded CSV/NDJSON/list records; times stay ISO/JSON serializable."""
    ReplayConfig(instrument)
    if isinstance(source, str):
        if len(source.encode("utf-8")) > MAX_TEXT_BYTES:
            raise ValueError("Replay text exceeds the 16 MB local limit")
        if format == "csv":
            reader = csv.DictReader(io.StringIO(source))
            if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise ValueError("Replay CSV needs distinct canonical column names")
            records = list(reader)
        elif format == "ndjson":
            try:
                records = [json.loads(line) for line in source.splitlines() if line.strip()]
            except ValueError:
                raise ValueError("Replay NDJSON must contain one JSON object per line") from None
        else:
            raise ValueError("Text replay format must be csv or ndjson")
    elif isinstance(source, list) and format == "records":
        records = source
    else:
        raise ValueError("Provide canonical replay records, CSV or NDJSON")
    if not 1 <= len(records) <= MAX_RECORDS:
        raise ValueError("Replay requires 1..100,000 observations")
    allowed = {
        "timestamp",
        "available_at",
        "availability_assumed",
        "sequence",
        "instrument",
        "type",
        "bid",
        "ask",
        "bid_size",
        "ask_size",
        "bids",
        "asks",
        "price",
        "quantity",
        "aggressor",
    }
    result, seen, unsequenced = [], set(), set()
    level_count = 0
    for index, record in enumerate(records):
        if not isinstance(record, dict) or set(record) - allowed:
            raise ValueError("Replay records must use the documented canonical fields")
        if record.get("instrument") != instrument:
            raise ValueError("Every replay record must match the selected instrument exactly")
        kind = record.get("type")
        if kind not in {"quote", "depth", "trade"}:
            raise ValueError("Replay type must be quote, depth or trade")
        observed_value = record.get("timestamp")
        if not isinstance(observed_value, (str, datetime)):
            raise ValueError("Replay timestamp must be a timezone-aware ISO timestamp")
        observed = timestamp(observed_value)
        available = timestamp(record.get("available_at") or observed)
        if available < observed:
            raise ValueError("Replay availability cannot precede observation time")
        if "availability_assumed" in record and type(record["availability_assumed"]) is not bool:
            raise ValueError("availability_assumed must be a boolean in normalized records")
        raw_sequence = record.get("sequence")
        if raw_sequence is None or raw_sequence == "":
            collision = (kind, observed)
            if collision in unsequenced:
                raise ValueError(
                    "Equal-time observations of one type require explicit unique sequences"
                )
            unsequenced.add(collision)
            sequence = index
        else:
            if isinstance(raw_sequence, bool) or not re.fullmatch(r"\d{1,16}", str(raw_sequence)):
                raise ValueError("Replay sequence must be a nonnegative integer")
            sequence = int(raw_sequence)
        identity = (kind, observed, sequence)
        if identity in seen:
            raise ValueError("Duplicate replay event identity would reuse liquidity")
        seen.add(identity)
        normalized = {
            "timestamp": observed.isoformat(),
            "available_at": available.isoformat(),
            "availability_assumed": bool(
                record.get("availability_assumed", not record.get("available_at"))
            ),
            "sequence": sequence,
            "instrument": instrument,
            "type": kind,
        }
        if kind in {"quote", "depth"}:
            if kind == "quote":
                bids = [
                    [
                        _number(record.get("bid"), "bid", positive=True),
                        _number(record.get("bid_size"), "bid size"),
                    ]
                ]
                asks = [
                    [
                        _number(record.get("ask"), "ask", positive=True),
                        _number(record.get("ask_size"), "ask size"),
                    ]
                ]
                normalized.update(
                    bid=bids[0][0], bid_size=bids[0][1], ask=asks[0][0], ask_size=asks[0][1]
                )
            else:
                bids, asks = (
                    _levels(record.get("bids"), "bids"),
                    _levels(record.get("asks"), "asks"),
                )
            if bids and asks and bids[0][0] > asks[0][0]:
                raise ValueError("Crossed quote/depth snapshots are not supported")
            normalized.update(bids=bids, asks=asks)
            level_count += len(bids) + len(asks)
            if level_count > 200_000:
                raise ValueError("Replay exceeds the 200,000 displayed-level observation budget")
        else:
            aggressor = record.get("aggressor") or "unknown"
            if aggressor not in {"buy", "sell", "unknown"}:
                raise ValueError("Trade aggressor must be buy, sell or unknown")
            normalized.update(
                price=_number(record.get("price"), "trade price", positive=True),
                quantity=_number(record.get("quantity"), "trade base quantity", positive=True),
                aggressor=aggressor,
            )
        result.append(normalized)
    return sorted(
        result, key=lambda event: (event["available_at"], event["sequence"], event["timestamp"])
    )


@dataclass
class _Order:
    identity: str
    submitted: int
    side: str
    order_type: str
    remaining: float
    limit: float | None
    arrived: datetime
    expires: datetime
    clock: dict
    requested: float
    fixed_paid: bool = False
    filled: float = 0
    status: str = "pending"
    budget_remaining: float | None = None


@dataclass
class _Ledger:
    cash: float
    units: float = 0
    basis: float = 0
    realized: float = 0
    fees: float = 0
    closed_pnls: list[float] = field(default_factory=list)


def _step(quantity: float, step: float) -> float:
    if step == 0:
        return max(0.0, quantity)
    return max(
        0.0,
        float(
            (Decimal(str(quantity)) / Decimal(str(step))).to_integral_value(rounding=ROUND_FLOOR)
            * Decimal(str(step))
        ),
    )


def _done(order: _Order) -> bool:
    return order.remaining <= order.requested * 1e-12


def replay_backtest(
    bars: list[Bar],
    decisions: list[Decision | dict | None],
    execution_config: ExecutionConfig | None,
    records: str | list[dict],
    replay_config: ReplayConfig | dict,
    *,
    start_index: int = 0,
    end_index: int | None = None,
    format: str = "records",
) -> dict:
    """Replay known observations; exact-time new data never retroactively fills arrivals.

    available_at is the paper-observation clock. Delayed trade evidence is not
    backdated into earlier cash/equity. This deliberately avoids exact-venue claims.
    """
    validate_bars(bars)
    cfg = execution_config or ExecutionConfig()
    replay = (
        replay_config if isinstance(replay_config, ReplayConfig) else ReplayConfig(**replay_config)
    )
    events = parse_replay(records, format, instrument=replay.instrument)
    stop = len(bars) if end_index is None else end_index
    if (
        type(start_index) is not int
        or type(stop) is not int
        or not 0 <= start_index < stop <= len(bars)
        or stop - start_index < 2
        or len(decisions) != len(bars)
    ):
        raise ValueError("Replay needs aligned decisions and at least two active bars")
    if any(
        (b.timestamp - a.timestamp).total_seconds() < cfg.bar_seconds
        for a, b in zip(bars, bars[1:])
    ):
        raise ValueError("Configured bar duration overlaps the next bar")
    ending = bars[stop - 1].timestamp + timedelta(seconds=cfg.bar_seconds)
    ledger = _Ledger(cfg.initial_cash)
    fills: list[dict] = []
    equity: list[dict] = []
    history: list[dict] = []
    summaries: dict[str, dict] = {}
    active: dict[str, _Order] = {}
    canceled: set[str] = set()
    queue_ahead: dict[tuple[str, float], float] = {}
    own_consumed: dict[tuple[str, float], float] = {}
    displayed: dict[tuple[str, float], float] = {}
    remaining_book: dict[tuple[str, float], float] = {}
    book_time: datetime | None = None
    book_available: datetime | None = None
    bids: list[float] = []
    asks: list[float] = []
    timeline: list[tuple[datetime, int, int, str, Any]] = []
    serial = 0

    def schedule(when: datetime, priority: int, kind: str, value: Any) -> None:
        nonlocal serial
        serial += 1
        heapq.heappush(timeline, (when, priority, serial, kind, value))

    def record_order(identity: str, submitted: int, status: str, now: datetime, **extra) -> None:
        summaries[identity] = {
            "id": identity,
            "submitted_bar": submitted,
            "fill_bar": None,
            "status": status,
            **extra,
        }
        history.append({**summaries[identity], "at": now.isoformat()})

    def fresh(now: datetime) -> bool:
        return (
            book_time is not None
            and book_available is not None
            and book_available < now
            and (now - book_time).total_seconds() * 1000 <= replay.max_quote_age_ms
            and bool(bids)
            and bool(asks)
        )

    def reservations(exclude: str | None = None) -> tuple[float, float]:
        cash = units = 0.0
        rate = max(cfg.fee_bps, replay.maker_fee_bps or cfg.fee_bps) / 10_000
        for order in active.values():
            if order.identity == exclude or order.status != "resting":
                continue
            if order.side == "buy":
                assert order.limit is not None
                cash += order.remaining * order.limit * (1 + rate) + (
                    0 if order.fixed_paid else cfg.fixed_fee
                )
            else:
                units += order.remaining
        return cash, units

    def execute(
        order: _Order,
        quantity: float,
        price: float,
        now: datetime,
        *,
        maker: bool,
        reference: float,
        evidence: dict,
    ) -> float:
        rate = (
            replay.maker_fee_bps if maker and replay.maker_fee_bps is not None else cfg.fee_bps
        ) / 10_000
        reserved_cash, reserved_units = reservations(order.identity)
        fixed = 0 if order.fixed_paid else cfg.fixed_fee
        quantity = min(quantity, order.remaining)
        if order.side == "buy":
            budget = ledger.cash - reserved_cash
            if order.budget_remaining is not None:
                budget = min(budget, order.budget_remaining)
            quantity = min(quantity, max(0, budget - fixed) / (price * (1 + rate)))
        else:
            quantity = min(quantity, max(0, ledger.units - reserved_units))
        quantity = _step(quantity, replay.quantity_step)
        if quantity <= 0:
            return 0.0
        notional = quantity * price
        commission = notional * rate + fixed
        if order.side == "sell" and ledger.cash + notional - commission < reserved_cash - 1e-8:
            return 0.0
        if not all(math.isfinite(value) for value in (quantity, notional, commission)):
            raise ValueError("Replay execution exceeds finite numeric limits")
        realized = 0.0
        if order.side == "buy":
            ledger.cash -= notional + commission
            ledger.units += quantity
            ledger.basis += notional + commission
            if order.budget_remaining is not None:
                order.budget_remaining = max(0, order.budget_remaining - notional - commission)
        else:
            allocated = ledger.basis * quantity / ledger.units
            realized = notional - commission - allocated
            ledger.cash += notional - commission
            ledger.units -= quantity
            ledger.basis -= allocated
            ledger.realized += realized
            ledger.closed_pnls.append(realized)
            if ledger.units == 0:
                ledger.basis = 0.0
        if ledger.cash < -1e-7 or ledger.units < 0:
            raise ArithmeticError("Replay portfolio constraint violation")
        ledger.cash = max(0.0, ledger.cash)
        ledger.fees += commission
        order.remaining = max(0.0, order.remaining - quantity)
        order.filled += quantity
        order.fixed_paid = True
        fill_bar = min(
            stop - 1,
            max(start_index, bisect.bisect_right([bar.timestamp for bar in bars], now) - 1),
        )
        mid = (bids[0] + asks[0]) / 2 if bids and asks else reference
        half_spread = (asks[0] - bids[0]) / 2 if bids and asks else 0
        fills.append(
            {
                **order.clock,
                "order_id": order.identity,
                "submitted_bar": order.submitted,
                "fill_bar": fill_bar,
                "filled_at": now.isoformat(),
                "instrument": replay.instrument,
                "side": order.side,
                "order_type": order.order_type,
                "liquidity_role": "maker_assumption" if maker else "taker",
                "quantity": quantity,
                "price": price,
                "market_open": bars[fill_bar].open,
                "reference_quote_price": reference,
                "quote_mid": mid,
                "quote_bid": bids[0] if bids else None,
                "quote_ask": asks[0] if asks else None,
                "notional": notional,
                "fee": commission,
                "proportional_fee": notional * rate,
                "fixed_fee": fixed,
                "slippage_cost": quantity * abs(price - reference),
                "spread_cost": 0 if maker else quantity * half_spread,
                "depth_impact_cost": 0
                if maker
                else quantity * max(0, abs(reference - mid) - half_spread),
                "realized_pnl": realized,
                "cash_after": ledger.cash,
                "units_after": ledger.units,
                "cost_basis_after": ledger.basis,
                "evidence": evidence,
            }
        )
        summaries[order.identity] = {
            "id": order.identity,
            "submitted_bar": order.submitted,
            "fill_bar": fill_bar,
            "status": "filled" if _done(order) else "partially_filled",
            "filled_quantity": order.filled,
            "remaining_quantity": order.remaining,
        }
        history.append({**summaries[order.identity], "at": now.isoformat(), **order.clock})
        return quantity

    for event in events:
        observed = timestamp(event["timestamp"])
        available = (
            observed + _milliseconds(cfg.data_delay_ms)
            if event["availability_assumed"]
            else timestamp(event["available_at"])
        )
        schedule(available, 3, "market_data", {**event, "available_at": available.isoformat()})
    known_ids: set[str] = set()
    planned_indices: dict[str, int] = {}
    planned_clocks: dict[str, dict] = {}
    for index in range(start_index, stop):
        schedule(bars[index].timestamp + timedelta(seconds=cfg.bar_seconds), 0, "valuation", index)
        value = decisions[index]
        if value is None:
            continue
        if isinstance(value, Decision):
            intent = asdict(value)
        elif isinstance(value, dict):
            intent = dict(value)
        else:
            raise ValueError("Replay decisions must be Decision records, intent objects or None")
        if set(intent) - {
            "target_weight",
            "buy_cash",
            "available_at",
            "side",
            "quantity",
            "order_type",
            "limit_price",
            "ttl_ms",
            "client_id",
            "cancel_id",
        }:
            raise ValueError("Unknown replay intent field")
        if "cancel_id" in intent:
            if set(intent) - {"cancel_id", "available_at", "client_id"} or not isinstance(
                intent["cancel_id"], str
            ):
                raise ValueError(
                    "Cancellation needs a target ID, optional client ID and readiness only"
                )
        else:
            if (
                sum(
                    intent.get(name) is not None
                    for name in ("quantity", "buy_cash", "target_weight")
                )
                != 1
            ):
                raise ValueError("Choose exactly one replay sizing rule")
            if intent.get("order_type", "market") not in {"market", "limit"}:
                raise ValueError("Replay supports market and limit orders only")
            if (
                intent.get("order_type", "market") == "market"
                and intent.get("limit_price") is not None
            ):
                raise ValueError("A limit price requires order_type=limit")
            if intent.get("quantity") is not None:
                _number(intent["quantity"], "base quantity", positive=True)
                if intent.get("side") not in {"buy", "sell"}:
                    raise ValueError("Explicit quantities require side=buy or side=sell")
            else:
                if intent.get("side") is not None:
                    raise ValueError("An explicit side is used only with explicit base quantity")
                if intent.get("buy_cash") is not None:
                    _number(intent["buy_cash"], "quote cash budget", positive=True)
                elif _number(intent["target_weight"], "target weight") > 1:
                    raise ValueError("Replay is long-only spot, without leverage or shorts")
            if intent.get("order_type", "market") == "limit":
                _number(intent.get("limit_price"), "limit price", positive=True)
            ttl = _number(intent.get("ttl_ms", replay.limit_ttl_ms), "limit TTL", positive=True)
            if ttl > 31_536_000_000:
                raise ValueError("Limit TTL exceeds 365 days")
        identity = intent.get("client_id", f"order-{index}")
        if (
            not isinstance(identity, str)
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", identity)
            or identity in known_ids
        ):
            raise ValueError("Replay client IDs must be distinct simple identifiers")
        known_ids.add(identity)
        planned_indices[identity] = index
        closed = bars[index].timestamp + timedelta(seconds=cfg.bar_seconds)
        market_available = closed + _milliseconds(cfg.data_delay_ms)
        decision_at = (
            max(market_available, timestamp(intent["available_at"]))
            if intent.get("available_at")
            else market_available
        )
        arrival = decision_at + _milliseconds(cfg.latency_ms)
        clock = {
            "decision_bar_open": bars[index].timestamp.isoformat(),
            "nominal_close": closed.isoformat(),
            "market_available_at": market_available.isoformat(),
            "decision_at": decision_at.isoformat(),
            "submitted_at": decision_at.isoformat(),
            "eligible_at": arrival.isoformat(),
        }
        planned_clocks[identity] = clock
        schedule(
            arrival, 1 if "cancel_id" in intent else 2, "arrival", (identity, index, intent, clock)
        )

    while timeline:
        now, _, _, kind, value = heapq.heappop(timeline)
        if now > ending or (now == ending and kind != "valuation"):
            continue
        if kind == "valuation":
            bar = bars[value]
            marked = ledger.cash + ledger.units * bar.close
            if not math.isfinite(marked):
                raise ValueError("Replay equity exceeds finite numeric limits")
            equity.append(
                {
                    "timestamp": bar.timestamp.isoformat(),
                    "valuation_at": now.isoformat(),
                    "equity": marked,
                    "cash": ledger.cash,
                    "units": ledger.units,
                    "position_value": ledger.units * bar.close,
                    "cost_basis": ledger.basis,
                    "average_cost": ledger.basis / ledger.units if ledger.units else None,
                    "realized_pnl": ledger.realized,
                    "unrealized_pnl": ledger.units * bar.close - ledger.basis,
                    "fees_paid": ledger.fees,
                }
            )
            continue
        if kind == "expiry":
            order = active.pop(value, None)
            if order is not None:
                record_order(
                    order.identity,
                    order.submitted,
                    "expired_ttl",
                    now,
                    filled_quantity=order.filled,
                    remaining_quantity=order.remaining,
                )
            continue
        if kind == "arrival":
            identity, submitted, intent, clock = value
            if "cancel_id" in intent:
                target = intent["cancel_id"]
                if not isinstance(target, str) or target not in known_ids:
                    record_order(identity, submitted, "cancel_not_found", now)
                else:
                    canceled.add(target)
                    order = active.pop(target, None)
                    if order:
                        record_order(
                            target,
                            order.submitted,
                            "canceled",
                            now,
                            filled_quantity=order.filled,
                            remaining_quantity=order.remaining,
                        )
                    record_order(identity, submitted, "cancel_requested", now, cancel_id=target)
                continue
            if identity in canceled:
                record_order(identity, submitted, "canceled_before_arrival", now, **clock)
                continue
            if not fresh(now):
                record_order(identity, submitted, "rejected_missing_or_stale_quote", now, **clock)
                continue
            reserved_cash, reserved_units = reservations()
            free_cash, free_units = (
                max(0, ledger.cash - reserved_cash),
                max(0, ledger.units - reserved_units),
            )
            order_type = intent.get("order_type", "market")
            if order_type not in {"market", "limit"}:
                raise ValueError("Replay order type is market or limit")
            limit = (
                _number(intent.get("limit_price"), "limit price", positive=True)
                if order_type == "limit"
                else None
            )
            ttl = _number(intent.get("ttl_ms", replay.limit_ttl_ms), "limit TTL", positive=True)
            if ttl > 31_536_000_000:
                raise ValueError("Limit TTL exceeds 365 days")
            side = intent.get("side")
            cash_budget = None
            if intent.get("quantity") is not None:
                if (
                    side not in {"buy", "sell"}
                    or intent.get("buy_cash") is not None
                    or intent.get("target_weight") is not None
                ):
                    raise ValueError(
                        "Explicit quantity needs one buy/sell side and no other sizing rule"
                    )
                quantity = _number(intent["quantity"], "base quantity", positive=True)
            elif intent.get("buy_cash") is not None:
                side = "buy"
                budget = min(
                    free_cash, _number(intent["buy_cash"], "quote cash budget", positive=True)
                )
                cash_budget = budget
                reference = limit if limit is not None else asks[0] * (1 + cfg.slippage_bps / 10000)
                quantity = max(0, budget - cfg.fixed_fee) / (
                    reference * (1 + max(cfg.fee_bps, replay.maker_fee_bps or cfg.fee_bps) / 10000)
                )
            elif intent.get("target_weight") is not None:
                weight = _number(intent["target_weight"], "target weight")
                if weight > 1:
                    raise ValueError("Replay is long-only spot; target weight must be <=1")
                mid = (bids[0] + asks[0]) / 2
                desired = weight * (ledger.cash + ledger.units * mid) - ledger.units * mid
                side = "buy" if desired >= 0 else "sell"
                reference = (
                    limit
                    if limit is not None
                    else (
                        asks[0] * (1 + cfg.slippage_bps / 10000)
                        if side == "buy"
                        else bids[0] * (1 - cfg.slippage_bps / 10000)
                    )
                )
                factor = (
                    reference * (1 + cfg.fee_bps / 10000) / mid
                    if side == "buy"
                    else reference * (1 - cfg.fee_bps / 10000) / mid
                )
                denominator = mid * (1 + weight * (factor - 1))
                signed = (
                    weight * (ledger.cash + ledger.units * mid - cfg.fixed_fee) - ledger.units * mid
                ) / denominator
                quantity = max(0, signed if side == "buy" else -signed)
                if abs(desired) <= max(1e-12, cfg.initial_cash * 1e-12):
                    quantity = 0
            else:
                raise ValueError("Replay intent needs quantity, buy_cash or target_weight")
            assert side in {"buy", "sell"}
            reference = limit if limit is not None else (asks[0] if side == "buy" else bids[0])
            if side == "buy":
                quantity = min(
                    quantity,
                    max(0, free_cash - cfg.fixed_fee)
                    / (
                        reference
                        * (1 + max(cfg.fee_bps, replay.maker_fee_bps or cfg.fee_bps) / 10000)
                    ),
                )
            else:
                quantity = min(quantity, free_units)
            quantity = _step(quantity, replay.quantity_step)
            if quantity <= 0 or quantity * reference < replay.min_notional:
                record_order(identity, submitted, "rejected_size_or_cash_constraint", now, **clock)
                continue
            order = _Order(
                identity,
                submitted,
                side,
                order_type,
                quantity,
                limit,
                now,
                now + _milliseconds(ttl),
                clock,
                quantity,
            )
            order.budget_remaining = cash_budget
            levels = asks if side == "buy" else bids
            book_side = "ask" if side == "buy" else "bid"
            for price in levels:
                execution_price = price * (
                    1 + cfg.slippage_bps / 10000 if side == "buy" else 1 - cfg.slippage_bps / 10000
                )
                if limit is not None and (
                    execution_price > limit if side == "buy" else execution_price < limit
                ):
                    break
                key = (book_side, price)
                capacity = min(
                    remaining_book.get(key, 0),
                    max(
                        0,
                        displayed.get(key, 0) * replay.participation_rate
                        - own_consumed.get(key, 0),
                    ),
                )
                used = execute(
                    order,
                    capacity,
                    execution_price,
                    now,
                    maker=False,
                    reference=price,
                    evidence={
                        "kind": "displayed_depth",
                        "quote_timestamp": book_time.isoformat() if book_time else None,
                        "quote_available_at": book_available.isoformat()
                        if book_available
                        else None,
                        "displayed_quantity": displayed.get(key, 0),
                    },
                )
                remaining_book[key] = max(0, remaining_book.get(key, 0) - used)
                own_consumed[key] = own_consumed.get(key, 0) + used
                if _done(order):
                    break
            if _done(order):
                continue
            if order_type == "market":
                record_order(
                    identity,
                    submitted,
                    "partially_filled_ioc_canceled"
                    if order.filled
                    else "canceled_no_displayed_liquidity",
                    now,
                    filled_quantity=order.filled,
                    remaining_quantity=order.remaining,
                    **clock,
                )
                continue
            if len(active) >= 100:
                record_order(identity, submitted, "rejected_live_order_budget", now, **clock)
                continue
            assert limit is not None
            key = ("bid" if side == "buy" else "ask", limit)
            if key not in displayed:
                record_order(
                    identity,
                    submitted,
                    "canceled_unobserved_limit_level",
                    now,
                    filled_quantity=order.filled,
                    remaining_quantity=order.remaining,
                    **clock,
                )
                continue
            if not any(other.side == side and other.limit == limit for other in active.values()):
                queue_ahead[key] = displayed[key] * replay.queue_ahead_multiplier
            order.status = "resting"
            active[identity] = order
            record_order(
                identity,
                submitted,
                "resting",
                now,
                filled_quantity=order.filled,
                remaining_quantity=order.remaining,
                queue_ahead=queue_ahead[key],
                **clock,
            )
            schedule(order.expires, 1, "expiry", identity)
            continue
        event = value
        observed = timestamp(event["timestamp"])
        if event["type"] in {"quote", "depth"}:
            if book_time is not None and observed < book_time:
                continue
            book_time, book_available = observed, now
            displayed = {("bid", price): quantity for price, quantity in event["bids"]} | {
                ("ask", price): quantity for price, quantity in event["asks"]
            }
            remaining_book = {
                key: max(0, quantity - own_consumed.get(key, 0))
                for key, quantity in displayed.items()
            }
            bids = sorted(
                [
                    price
                    for side, price in displayed
                    if side == "bid" and displayed[(side, price)] > 0
                ],
                reverse=True,
            )
            asks = sorted(
                [
                    price
                    for side, price in displayed
                    if side == "ask" and displayed[(side, price)] > 0
                ]
            )
            continue
        aggressor = event["aggressor"]
        if aggressor == "unknown":
            continue
        side = "buy" if aggressor == "sell" else "sell"
        key = ("bid" if side == "buy" else "ask", event["price"])
        if book_time is None or observed >= book_time:
            remaining_book[key] = max(0, remaining_book.get(key, 0) - event["quantity"])
        eligible = [
            order
            for order in active.values()
            if order.side == side
            and order.limit == event["price"]
            and observed > order.arrived
            and now < order.expires
        ]
        if not eligible or not fresh(now):
            continue
        ahead = queue_ahead.get(key, 0)
        consume_ahead = min(ahead, event["quantity"])
        queue_ahead[key] = ahead - consume_ahead
        trade_budget = min(
            event["quantity"] - consume_ahead,
            event["quantity"] * replay.participation_rate,
            max(0, displayed.get(key, 0) * replay.participation_rate - own_consumed.get(key, 0)),
        )
        for order in sorted(eligible, key=lambda item: (item.arrived, item.identity)):
            if trade_budget <= 0:
                break
            used = execute(
                order,
                trade_budget,
                event["price"],
                now,
                maker=True,
                reference=event["price"],
                evidence={
                    "kind": "subsequent_aggressor_trade",
                    "trade_timestamp": event["timestamp"],
                    "trade_available_at": event["available_at"],
                    "trade_quantity": event["quantity"],
                    "queue_ahead_before": ahead,
                },
            )
            trade_budget -= used
            own_consumed[key] = own_consumed.get(key, 0) + used
            if _done(order):
                active.pop(order.identity, None)
    for identity, order in active.items():
        record_order(
            identity,
            order.submitted,
            "expired_end_of_data",
            ending,
            filled_quantity=order.filled,
            remaining_quantity=order.remaining,
            **order.clock,
        )
    for identity in sorted(known_ids - summaries.keys(), key=planned_indices.__getitem__):
        record_order(
            identity,
            planned_indices[identity],
            "canceled_before_arrival" if identity in canceled else "expired_before_arrival",
            ending,
            **planned_clocks[identity],
        )
    metrics = calculate_metrics(
        [row["equity"] for row in equity], cfg, fills, ledger.closed_pnls, bars[start_index:stop]
    )
    metrics["depth_impact_cost"] = sum(fill["depth_impact_cost"] for fill in fills)
    peak = cfg.initial_cash
    for row in equity:
        peak = max(peak, row["equity"])
        row["drawdown"] = row["equity"] / peak - 1
    return {
        "metrics": metrics,
        "equity": equity,
        "fills": fills,
        "orders": list(summaries.values()),
        "order_events": history,
        "config": asdict(cfg),
        "replay": {
            "configuration": asdict(replay),
            "records": len(events),
            "clock": "receipt-time paper replay; new equal-time observations cannot fill arrivals",
            "quantity_unit": "base units",
            "price_unit": "quote currency per base unit",
            "fixed_fee_policy": "once per order, on first actual fill",
            "data_level": "absolute displayed quote/depth snapshots and optional aggressor trade prints",
        },
        "window": {"start_index": start_index, "end_index": stop},
        "warnings": [
            "Observed single-instrument long-only spot paper replay; no leverage, borrow, funding, dividends, options or real-money routing.",
            "L2 snapshots do not identify orders or reconstruct exact queue position. Passive fills are conditional on an explicit queue-ahead assumption and subsequent exact-price aggressor prints.",
            "Own-consumed capacity is deducted by side/price across later snapshots; unchanged snapshots never replenish it. This conservative bound can underfill real replenishment.",
            "Fill and cash timestamps use when evidence is available; delayed trade evidence is never backdated. Quote age is checked against the observation timestamp.",
            "Market orders are IOC. Partial limit remainders rest only at observed levels and reserve cash/units. Final orders expire; holdings are marked at source-bar closes without liquidation.",
            "Actual quoted spread is used. ExecutionConfig.spread_bps is ignored to avoid charging a fabricated spread again; additional slippage remains an explicit assumption.",
        ],
    }


def replay_benchmark(
    bars: list[Bar],
    execution_config: ExecutionConfig | None,
    records: str | list[dict],
    replay_config: ReplayConfig | dict,
    *,
    start_index: int = 0,
    end_index: int | None = None,
    format: str = "records",
) -> dict:
    decisions: list[Decision | dict | None] = [None] * len(bars)
    if type(start_index) is int and 0 <= start_index < len(bars):
        decisions[start_index] = Decision(target_weight=1)
    return replay_backtest(
        bars,
        decisions,
        execution_config,
        records,
        replay_config,
        start_index=start_index,
        end_index=end_index,
        format=format,
    )
