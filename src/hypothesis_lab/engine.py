"""Small, explicit long-only spot execution and accounting engine."""

from __future__ import annotations

import heapq
import math
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

from .data import Bar, timestamp, validate_bars


@dataclass(frozen=True)
class Decision:
    """Intent from a completed bar, filled at the first later eligible open.

    buy_cash includes commission and fixed fees. Optional available_at declares
    later inference/readiness; the engine never lets it predate bar availability.
    """

    target_weight: float | None = None
    buy_cash: float | None = None
    available_at: str | datetime | None = None

    def __post_init__(self) -> None:
        if (self.target_weight is None) == (self.buy_cash is None):
            raise ValueError("Choose exactly one of target_weight or buy_cash")
        if any(isinstance(value, bool) for value in (self.target_weight, self.buy_cash)):
            raise ValueError("Decision amounts must be numbers, not booleans")
        if self.target_weight is not None and (
            not math.isfinite(self.target_weight) or not 0 <= self.target_weight <= 1
        ):
            raise ValueError("Target weight must be between zero and one")
        if self.buy_cash is not None and (not math.isfinite(self.buy_cash) or self.buy_cash <= 0):
            raise ValueError("Buy budget must be positive and finite")
        if self.available_at is not None:
            object.__setattr__(self, "available_at", timestamp(self.available_at).isoformat())


@dataclass(frozen=True)
class ExecutionConfig:
    initial_cash: float = 10_000
    fee_bps: float = 10
    slippage_bps: float = 5
    periods_per_year: float = 365
    bar_seconds: float = 86400
    fixed_fee: float = 0
    spread_bps: float = 0
    data_delay_ms: float = 0
    latency_ms: float = 0

    def __post_init__(self) -> None:
        if not all(
            isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
            for x in asdict(self).values()
        ):
            raise ValueError("Execution parameters must be finite")
        if self.initial_cash <= 0 or self.periods_per_year <= 0 or self.bar_seconds <= 0:
            raise ValueError(
                "Initial cash, bar duration and annualization frequency must be positive"
            )
        if not 0 <= self.fee_bps < 10_000 or not 0 <= self.slippage_bps < 10_000:
            raise ValueError("Fee/slippage must be in [0,10000) basis points")
        if self.fixed_fee < 0 or self.spread_bps < 0:
            raise ValueError("Fixed fee and full bid/ask spread must be nonnegative")
        if self.slippage_bps + self.spread_bps / 2 >= 10_000:
            raise ValueError("Slippage plus half-spread must be below 10000 basis points")
        if (
            not 0 <= self.data_delay_ms <= 31_536_000_000
            or not 0 <= self.latency_ms <= 31_536_000_000
        ):
            raise ValueError("Data/order delay must be between zero and 365 days in milliseconds")


def _delay(milliseconds: float) -> timedelta:
    # Never round a positive sub-microsecond delay back to zero at a bar boundary.
    return timedelta(microseconds=math.ceil(milliseconds * 1000))


def backtest(
    bars: list[Bar],
    decisions: list[Decision | None],
    config: ExecutionConfig | None = None,
    *,
    start_index: int = 0,
    end_index: int | None = None,
) -> dict:
    validate_bars(bars)
    cfg = config or ExecutionConfig()
    if any(
        (b.timestamp - a.timestamp).total_seconds() < cfg.bar_seconds
        for a, b in zip(bars, bars[1:])
    ):
        raise ValueError("Configured bar duration overlaps the next bar")
    if len(decisions) != len(bars):
        raise ValueError("One close-time decision slot is required per bar")
    end = len(bars) if end_index is None else end_index
    if (
        isinstance(start_index, bool)
        or not isinstance(start_index, int)
        or isinstance(end, bool)
        or not isinstance(end, int)
        or not 0 <= start_index < end <= len(bars)
        or end - start_index < 2
    ):
        raise ValueError(
            "Evaluation bounds must select at least two bars: start inclusive, end exclusive"
        )
    if any(intent is not None and not isinstance(intent, Decision) for intent in decisions):
        raise ValueError("Decision slots must contain a Decision or None")
    fee = cfg.fee_bps / 10_000
    slip, half_spread = cfg.slippage_bps / 10_000, cfg.spread_bps / 20_000
    impact = slip + half_spread
    cash, units, cost_basis = cfg.initial_cash, 0.0, 0.0
    fills: list[dict[str, Any]] = []
    equity: list[dict[str, Any]] = []
    closed_pnls: list[float] = []
    orders: list[dict[str, Any]] = []
    order_events: list[dict[str, Any]] = []
    pending: list[tuple[datetime, int, Decision, dict[str, Any]]] = []
    for submitted in range(start_index, end):
        intent = decisions[submitted]
        if intent is None:
            continue
        nominal_close = bars[submitted].timestamp + timedelta(seconds=cfg.bar_seconds)
        market_available = nominal_close + _delay(cfg.data_delay_ms)
        decision_at = (
            max(market_available, timestamp(intent.available_at))
            if intent.available_at is not None
            else market_available
        )
        eligible_at = decision_at + _delay(cfg.latency_ms)
        clock = {
            "decision_bar_open": bars[submitted].timestamp.isoformat(),
            "nominal_close": nominal_close.isoformat(),
            "market_available_at": market_available.isoformat(),
            "decision_at": decision_at.isoformat(),
            "submitted_at": decision_at.isoformat(),
            "eligible_at": eligible_at.isoformat(),
        }
        heapq.heappush(pending, (eligible_at, submitted, intent, clock))
    cumulative_fees = 0.0
    cumulative_realized = 0.0
    for i in range(start_index, end):
        bar = bars[i]
        while pending and pending[0][0] <= bar.timestamp:
            eligible_at, submitted, intent, clock = heapq.heappop(pending)
            if submitted >= i:
                raise ArithmeticError("A decision cannot fill before its completed source bar")
            mark = cash + units * bar.open
            status = "no_change"
            if intent.buy_cash is not None:
                budget = min(cash, intent.buy_cash)
                delta = max(0, budget - cfg.fixed_fee) / (bar.open * (1 + impact) * (1 + fee))
                if budget <= cfg.fixed_fee:
                    status = "rejected_insufficient_cash_for_costs"
            else:
                weight = intent.target_weight
                assert weight is not None
                # Solve post-cost target weight using open as mark and actual execution cost.
                delta_value = weight * mark - units * bar.open
                if abs(delta_value) <= max(1e-12, cfg.initial_cash * 1e-12):
                    delta = 0.0
                elif delta_value > 0:
                    delta = (weight * (mark - cfg.fixed_fee) - units * bar.open) / (
                        bar.open * (1 + weight * ((1 + impact) * (1 + fee) - 1))
                    )
                    delta = min(
                        delta, max(0, cash - cfg.fixed_fee) / (bar.open * (1 + impact) * (1 + fee))
                    )
                    if cash <= cfg.fixed_fee:
                        delta = 0.0
                        status = "rejected_insufficient_cash_for_costs"
                    elif delta < 0:
                        delta = 0.0
                        status = "rejected_fixed_cost_exceeds_adjustment"
                else:
                    delta = (weight * (mark - cfg.fixed_fee) - units * bar.open) / (
                        bar.open * (1 - weight * (1 - (1 - impact) * (1 - fee)))
                    )
                    delta = max(delta, -units)
            if not all(math.isfinite(value) for value in (mark, delta, cost_basis)):
                raise ValueError("Portfolio exceeds finite numeric limits; rescale the experiment")
            if abs(delta * bar.open) > max(1e-12, cfg.initial_cash * 1e-12):
                side = "buy" if delta > 0 else "sell"
                price = bar.open * (1 + impact if delta > 0 else 1 - impact)
                qty = abs(delta)
                notional = qty * price
                proportional_fee = notional * fee
                charge = proportional_fee + cfg.fixed_fee
                projected_cash = (
                    cash - (notional + charge) if delta > 0 else cash + notional - charge
                )
                tolerance = max(1e-8, cfg.initial_cash * 1e-12)
                if not all(
                    math.isfinite(value) for value in (price, notional, charge, projected_cash)
                ):
                    raise ValueError(
                        "Execution exceeds finite numeric limits; rescale the experiment"
                    )
                if projected_cash < -tolerance:
                    orders.append(
                        {
                            "submitted_bar": submitted,
                            "fill_bar": i,
                            "status": "rejected_insufficient_cash_for_costs",
                        }
                    )
                    order_events.append({**clock, **orders[-1], "filled_at": None})
                    continue
                if delta > 0:
                    outflow = notional + charge
                    cost_basis += outflow
                    cash -= outflow
                    units += qty
                    realized_pnl = 0.0
                else:
                    allocated = cost_basis * qty / units
                    pnl = notional - charge - allocated
                    closed_pnls.append(pnl)
                    cost_basis -= allocated
                    units -= qty
                    cash += notional - charge
                    realized_pnl = pnl
                    if units == 0:
                        cost_basis = 0.0
                if cash < -tolerance or units < 0:
                    raise ArithmeticError("Portfolio constraint violation")
                cash, units = max(cash, 0.0), max(units, 0.0)
                cumulative_fees += charge
                cumulative_realized += realized_pnl
                fills.append(
                    {
                        **clock,
                        "filled_at": bar.timestamp.isoformat(),
                        "fill_bar": i,
                        "submitted_bar": submitted,
                        "queue_wait_ms": (bar.timestamp - eligible_at).total_seconds() * 1000,
                        "side": side,
                        "quantity": qty,
                        "price": price,
                        "fee": charge,
                        "proportional_fee": proportional_fee,
                        "fixed_fee": cfg.fixed_fee,
                        "notional": notional,
                        "market_open": bar.open,
                        "slippage_cost": qty * bar.open * slip,
                        "spread_cost": qty * bar.open * half_spread,
                        "realized_pnl": realized_pnl,
                        "cash_after": cash,
                        "units_after": units,
                        "cost_basis_after": cost_basis,
                        "requested_buy_cash": intent.buy_cash,
                        "cash_limited": intent.buy_cash is not None
                        and notional + charge < intent.buy_cash - 1e-7,
                    }
                )
                status = "filled"
                orders.append({"submitted_bar": submitted, "fill_bar": i, "status": status})
                order_events.append({**clock, **orders[-1], "filled_at": bar.timestamp.isoformat()})
            else:
                orders.append({"submitted_bar": submitted, "fill_bar": i, "status": status})
                order_events.append({**clock, **orders[-1], "filled_at": None})
        equity.append(
            {
                "timestamp": bar.timestamp.isoformat(),
                "equity": cash + units * bar.close,
                "cash": cash,
                "units": units,
                "valuation_at": (bar.timestamp + timedelta(seconds=cfg.bar_seconds)).isoformat(),
                "position_value": units * bar.close,
                "cost_basis": cost_basis,
                "average_cost": cost_basis / units if units > 0 else None,
                "realized_pnl": cumulative_realized,
                "unrealized_pnl": units * bar.close - cost_basis,
                "fees_paid": cumulative_fees,
            }
        )
        if not all(
            math.isfinite(value) for value in (equity[-1]["equity"], cash, units, cost_basis)
        ):
            raise ValueError("Portfolio valuation exceeds finite numeric limits")
    for _, submitted, _, clock in sorted(pending):
        orders.append(
            {"submitted_bar": submitted, "fill_bar": None, "status": "expired_end_of_data"}
        )
        order_events.append(
            {
                **clock,
                **orders[-1],
                "filled_at": None,
                "reason": "No eligible supplied open remains in the evaluation window",
            }
        )
    active_bars = bars[start_index:end]
    metrics = calculate_metrics([r["equity"] for r in equity], cfg, fills, closed_pnls, active_bars)
    peak = cfg.initial_cash
    for row in equity:
        peak = max(peak, row["equity"])
        row["drawdown"] = row["equity"] / peak - 1
    warnings = [
        "Single-instrument, long-only spot; market/taker-style fills, no order-book depth, queue priority, volume participation, dividends, funding or tax model. Positions are marked at final close, not liquidated.",
        "Spread, slippage and delays are user assumptions. OHLC opens are reference trade prices, not observed bid/ask quotes. Full fills do not establish executable liquidity.",
    ]
    if cfg.data_delay_ms == 0 and cfg.latency_ms == 0:
        warnings.append(
            "Zero data/order delay is an idealized boundary assumption; it is not a measured real-world latency."
        )
    else:
        warnings.append(
            "Latency changes eligible fills. The first supplied open at/after readiness is used; even a small positive boundary delay can defer an entire bar. This is coarse bar quantization, not millisecond fill simulation."
        )
    if any(
        (b.timestamp - a.timestamp).total_seconds() > cfg.bar_seconds
        for a, b in zip(active_bars, active_bars[1:])
    ):
        warnings.append(
            "Market gaps exist: pending decisions fill at the next supplied open. Annualized statistics assume the configured sampling frequency and may be misleading with gaps."
        )
    return {
        "metrics": metrics,
        "equity": equity,
        "fills": fills,
        "orders": orders,
        "order_events": order_events,
        "window": {
            "start_index": start_index,
            "end_index": end,
            "first_bar_open": active_bars[0].timestamp.isoformat(),
            "last_bar_open": active_bars[-1].timestamp.isoformat(),
            "pre_window_intents_ignored": sum(
                intent is not None for intent in decisions[:start_index]
            ),
        },
        "config": asdict(cfg),
        "warnings": warnings,
    }


def calculate_metrics(
    values: list[float],
    cfg: ExecutionConfig,
    fills: list[dict],
    closed_pnls: list[float],
    bars: list[Bar],
) -> dict:
    if (
        not values
        or len(values) != len(bars)
        or any(not math.isfinite(value) or value < 0 for value in values)
    ):
        raise ValueError("Metric equity must be finite, nonnegative and aligned with market bars")
    previous, peak, max_drawdown = cfg.initial_cash, cfg.initial_cash, 0.0
    returns = []
    undefined_after_exhaustion = False
    for value in values:
        if previous == 0:
            undefined_after_exhaustion = True
            if value != 0:
                raise ValueError(
                    "A zero-equity portfolio cannot recover without external cash flows"
                )
            returns.append(0.0)
        else:
            returns.append(value / previous - 1)
        previous = value
        peak = max(peak, value)
        max_drawdown = min(max_drawdown, value / peak - 1)
    # First bar is pre-trade and not an elapsed close-to-close return.
    returns = returns[1:]
    vol = statistics.stdev(returns) if len(returns) > 1 else 0.0
    duration_days = (bars[-1].timestamp - bars[0].timestamp).total_seconds() / 86400
    total = values[-1] / cfg.initial_cash - 1
    if not math.isfinite(total) or any(not math.isfinite(value) for value in returns):
        raise ValueError("Returns exceed finite numeric limits; rescale the experiment")
    annualized = None
    if duration_days >= 365.2425 and total > -1:
        try:
            annualized = math.expm1(math.log1p(total) * 365.2425 / duration_days)
        except OverflowError:
            annualized = None
    losses = -sum(p for p in closed_pnls if p < 0)
    annualized_volatility = vol * math.sqrt(cfg.periods_per_year)
    sharpe = statistics.mean(returns) / vol * math.sqrt(cfg.periods_per_year) if vol > 0 else None
    return {
        "total_return": total,
        "annualized_return": annualized,
        "max_drawdown": max_drawdown,
        "annualized_volatility": annualized_volatility
        if len(returns) > 1
        and not undefined_after_exhaustion
        and math.isfinite(annualized_volatility)
        else None,
        "sharpe": sharpe
        if sharpe is not None and not undefined_after_exhaustion and math.isfinite(sharpe)
        else None,
        "turnover": sum(f["notional"] for f in fills) / cfg.initial_cash,
        "trade_count": len(fills),
        "closed_trade_count": len(closed_pnls),
        "profit_factor": sum(p for p in closed_pnls if p > 0) / losses if losses > 0 else None,
        "fees_paid": sum(f["fee"] for f in fills),
        "fixed_fees_paid": sum(f.get("fixed_fee", 0) for f in fills),
        "proportional_fees_paid": sum(f.get("proportional_fee", f["fee"]) for f in fills),
        "spread_cost": sum(f.get("spread_cost", 0) for f in fills),
        "slippage_cost": sum(f.get("slippage_cost", 0) for f in fills),
        "final_equity": values[-1],
    }


def benchmark(
    bars: list[Bar],
    config: ExecutionConfig | None = None,
    *,
    start_index: int = 0,
    end_index: int | None = None,
) -> dict:
    decisions: list[Decision | None] = [None] * len(bars)
    if (
        isinstance(start_index, int)
        and not isinstance(start_index, bool)
        and 0 <= start_index < len(bars)
    ):
        decisions[start_index] = Decision(target_weight=1)
    return backtest(bars, decisions, config, start_index=start_index, end_index=end_index)
