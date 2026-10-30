"""Independent audit reproductions: economic constraints, not implementation mirrors."""

import unittest
from datetime import UTC, datetime, timedelta

from hypothesis_lab.data import Bar
from hypothesis_lab.engine import ExecutionConfig
from hypothesis_lab.portfolio import portfolio_backtest

START = datetime(2024, 1, 1, tzinfo=UTC)


def at(second):
    return (START + timedelta(seconds=second)).isoformat()


def quote(symbol, second, price=100, size=100):
    return {
        "type": "quote",
        "instrument": symbol,
        "timestamp": at(second),
        "bid": price,
        "ask": price,
        "bid_size": size,
        "ask_size": size,
    }


class IndependentPortfolioAudit(unittest.TestCase):
    def run_book(self, instruments, events, targets, **execution):
        bars = [Bar(START + timedelta(minutes=i), 100, 101, 99, 100, 100) for i in range(5)]
        intents = [{"targets": targets[i]} if i in targets else None for i in range(5)]
        cfg = ExecutionConfig(
            initial_cash=1000, fee_bps=0, slippage_bps=0, bar_seconds=60, **execution
        )
        return portfolio_backtest(
            bars,
            intents,
            cfg,
            {
                "instruments": instruments,
                "events": events,
                "participation_rate": 1,
                "max_quote_age_ms": 2000,
            },
        )

    def test_strategy_cannot_cancel_mandatory_partial_liquidation(self):
        result = self.run_book(
            [{"symbol": "P", "kind": "perpetual", "allow_short": True}],
            [quote("P", 59), quote("P", 119, 10000, 0.25), quote("P", 179, 10000)],
            {0: {"P": -1}, 1: {"P": -1}},
        )
        self.assertEqual(result["metrics"]["margin_calls"], 1)
        self.assertEqual(
            result["portfolio"]["final_positions"]["P"]["units"],
            0,
            "Fresh strategy intent must not cancel the outstanding liquidation obligation",
        )

    def test_margin_history_before_evaluation_remains_effective(self):
        result = self.run_book(
            [
                {
                    "symbol": "P",
                    "kind": "perpetual",
                    "initial_margin_rate": 0.1,
                    "maintenance_margin_rate": 0.05,
                }
            ],
            [
                {
                    "type": "margin",
                    "instrument": "P",
                    "timestamp": at(-10),
                    "initial_margin_rate": 1,
                    "maintenance_margin_rate": 0.5,
                },
                quote("P", 59),
            ],
            {0: {"P": 20}},
        )
        self.assertEqual(
            result["fills"],
            [],
            "$2,000 notional requires $2,000 margin after the historical rate change, exceeding $1,000 collateral",
        )

    def test_european_option_cannot_physically_exercise_before_expiry(self):
        instruments = [
            {"symbol": "S", "kind": "equity"},
            {
                "symbol": "C",
                "kind": "option",
                "right": "call",
                "strike": 100,
                "multiplier": 100,
                "underlying": "S",
                "exercise_style": "european",
                "settlement_type": "physical",
                "expires_at": at(500),
            },
        ]
        with self.assertRaisesRegex(ValueError, "European|expiration|expiry"):
            self.run_book(
                instruments,
                [
                    quote("S", 59, 105),
                    quote("C", 59, 2),
                    {"type": "exercise", "instrument": "C", "timestamp": at(120), "quantity": 1},
                ],
                {0: {"C": 1}},
            )

    def test_cash_settled_option_cannot_deliver_underlying_shares(self):
        instruments = [
            {"symbol": "S", "kind": "equity"},
            {
                "symbol": "C",
                "kind": "option",
                "right": "call",
                "strike": 100,
                "multiplier": 100,
                "underlying": "S",
                "exercise_style": "american",
                "settlement_type": "cash",
                "expires_at": at(500),
            },
        ]
        with self.assertRaisesRegex(ValueError, "cash|physical|settlement"):
            self.run_book(
                instruments,
                [
                    quote("S", 59, 105),
                    quote("C", 59, 2),
                    {"type": "exercise", "instrument": "C", "timestamp": at(120), "quantity": 1},
                ],
                {0: {"C": 1}},
            )

    def test_closed_trade_profit_factor_includes_entry_and_exit_costs(self):
        result = self.run_book(
            [{"symbol": "S", "kind": "spot"}],
            [quote("S", 59, 100), quote("S", 119, 115)],
            {0: {"S": 1}, 1: {"S": 0}},
            fixed_fee=10,
        )
        self.assertEqual(result["metrics"]["final_equity"], 995)
        self.assertEqual(result["metrics"]["fees_paid"], 20)
        self.assertEqual(
            result["metrics"]["profit_factor"],
            0,
            "The only round trip lost $5 after both $10 fees, so it cannot be a profitable closed trade",
        )
