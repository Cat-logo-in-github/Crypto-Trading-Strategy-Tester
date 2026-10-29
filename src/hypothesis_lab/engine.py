"""Small, explicit long-only spot execution and accounting engine."""

from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Any

from .data import Bar, validate_bars


@dataclass(frozen=True)
class Decision:
    """Close-time intent, executed at the NEXT bar open. buy_cash is a fee-inclusive budget."""

    target_weight: float | None = None
    buy_cash: float | None = None

    def __post_init__(self) -> None:
        if (self.target_weight is None) == (self.buy_cash is None):
            raise ValueError("Choose exactly one of target_weight or buy_cash")
        if self.target_weight is not None and (
            not math.isfinite(self.target_weight) or not 0 <= self.target_weight <= 1
        ):
            raise ValueError("Target weight must be between zero and one")
        if self.buy_cash is not None and (not math.isfinite(self.buy_cash) or self.buy_cash <= 0):
            raise ValueError("Buy budget must be positive and finite")


@dataclass(frozen=True)
class ExecutionConfig:
    initial_cash: float = 10_000
    fee_bps: float = 10
    slippage_bps: float = 5
    periods_per_year: float = 365
    bar_seconds: float = 86400

    def __post_init__(self) -> None:
        if not all(math.isfinite(x) for x in asdict(self).values()):
            raise ValueError("Execution parameters must be finite")
        if self.initial_cash <= 0 or self.periods_per_year <= 0 or self.bar_seconds <= 0:
            raise ValueError(
                "Initial cash, bar duration and annualization frequency must be positive"
            )
        if not 0 <= self.fee_bps < 10_000 or not 0 <= self.slippage_bps < 10_000:
            raise ValueError("Fee/slippage must be in [0,10000) basis points")


def backtest(
    bars: list[Bar], decisions: list[Decision | None], config: ExecutionConfig | None = None
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
    fee, slip = cfg.fee_bps / 10_000, cfg.slippage_bps / 10_000
    cash, units, cost_basis = cfg.initial_cash, 0.0, 0.0
    fills: list[dict[str, Any]] = []
    equity: list[dict[str, Any]] = []
    closed_pnls: list[float] = []
    orders: list[dict[str, Any]] = []
    for i, bar in enumerate(bars):
        intent = decisions[i - 1] if i else None
        if intent is not None:
            mark = cash + units * bar.open
            if intent.buy_cash is not None:
                budget = min(cash, intent.buy_cash)
                delta = budget / (bar.open * (1 + slip) * (1 + fee))
            else:
                weight = intent.target_weight
                assert weight is not None
                # Solve post-cost target weight using open as mark and actual execution cost.
                delta_value = weight * mark - units * bar.open
                if delta_value >= 0:
                    delta = delta_value / (bar.open * (1 + weight * ((1 + slip) * (1 + fee) - 1)))
                    delta = min(delta, cash / (bar.open * (1 + slip) * (1 + fee)))
                else:
                    delta = delta_value / (bar.open * (1 - weight * (1 - (1 - slip) * (1 - fee))))
                    delta = max(delta, -units)
            if abs(delta) > 1e-10:
                side = "buy" if delta > 0 else "sell"
                price = bar.open * (1 + slip if delta > 0 else 1 - slip)
                qty = abs(delta)
                notional = qty * price
                charge = notional * fee
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
                if cash < -1e-7 or units < -1e-9:
                    raise ArithmeticError("Portfolio constraint violation")
                cash, units = max(cash, 0.0), max(units, 0.0)
                fills.append(
                    {
                        "decision_bar_open": bars[i - 1].timestamp.isoformat(),
                        "decision_at": (
                            bars[i - 1].timestamp + timedelta(seconds=cfg.bar_seconds)
                        ).isoformat(),
                        "filled_at": bar.timestamp.isoformat(),
                        "side": side,
                        "quantity": qty,
                        "price": price,
                        "fee": charge,
                        "notional": notional,
                        "market_open": bar.open,
                        "slippage_cost": qty * abs(price - bar.open),
                        "realized_pnl": realized_pnl,
                        "cash_after": cash,
                        "units_after": units,
                        "cost_basis_after": cost_basis,
                        "requested_buy_cash": intent.buy_cash,
                        "cash_limited": intent.buy_cash is not None
                        and notional + charge < intent.buy_cash - 1e-7,
                    }
                )
                orders.append({"submitted_bar": i - 1, "fill_bar": i, "status": "filled"})
            else:
                orders.append({"submitted_bar": i - 1, "fill_bar": i, "status": "no_change"})
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
                "realized_pnl": sum(closed_pnls),
                "unrealized_pnl": units * bar.close - cost_basis,
                "fees_paid": sum(fill["fee"] for fill in fills),
            }
        )
    if decisions[-1] is not None:
        orders.append(
            {"submitted_bar": len(bars) - 1, "fill_bar": None, "status": "expired_end_of_data"}
        )
    metrics = calculate_metrics([r["equity"] for r in equity], cfg, fills, closed_pnls, bars)
    peak = cfg.initial_cash
    for row in equity:
        peak = max(peak, row["equity"])
        row["drawdown"] = row["equity"] / peak - 1
    warnings = [
        "Single-instrument, long-only spot; no liquidity, spread, dividends, funding or tax model. Positions are marked at final close, not liquidated."
    ]
    if any(
        (b.timestamp - a.timestamp).total_seconds() > cfg.bar_seconds
        for a, b in zip(bars, bars[1:])
    ):
        warnings.append(
            "Market gaps exist: pending decisions fill at the next supplied open. Annualized statistics assume the configured sampling frequency and may be misleading with gaps."
        )
    return {
        "metrics": metrics,
        "equity": equity,
        "fills": fills,
        "orders": orders,
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
    previous, peak, max_drawdown = cfg.initial_cash, cfg.initial_cash, 0.0
    returns = []
    for value in values:
        returns.append(value / previous - 1)
        previous = value
        peak = max(peak, value)
        max_drawdown = min(max_drawdown, value / peak - 1)
    # First bar is pre-trade and not an elapsed close-to-close return.
    returns = returns[1:]
    vol = statistics.stdev(returns) if len(returns) > 1 else 0.0
    duration_days = (bars[-1].timestamp - bars[0].timestamp).total_seconds() / 86400
    total = values[-1] / cfg.initial_cash - 1
    annualized = None
    if duration_days >= 365.2425 and total > -1:
        annualized = math.expm1(math.log1p(total) * 365.2425 / duration_days)
    losses = -sum(p for p in closed_pnls if p < 0)
    return {
        "total_return": total,
        "annualized_return": annualized,
        "max_drawdown": max_drawdown,
        "annualized_volatility": vol * math.sqrt(cfg.periods_per_year)
        if len(returns) > 1
        else None,
        "sharpe": statistics.mean(returns) / vol * math.sqrt(cfg.periods_per_year)
        if vol > 0
        else None,
        "turnover": sum(f["notional"] for f in fills) / cfg.initial_cash,
        "trade_count": len(fills),
        "closed_trade_count": len(closed_pnls),
        "profit_factor": sum(p for p in closed_pnls if p > 0) / losses if losses > 0 else None,
        "fees_paid": sum(f["fee"] for f in fills),
        "final_equity": values[-1],
    }


def benchmark(bars: list[Bar], config: ExecutionConfig | None = None) -> dict:
    return backtest(bars, [Decision(target_weight=1)] + [None] * (len(bars) - 1), config)
