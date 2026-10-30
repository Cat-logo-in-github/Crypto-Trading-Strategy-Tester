"""Independent contract cash accounting and event-clock expectations."""

import copy
import json
import unittest
from datetime import UTC, datetime, timedelta

from hypothesis_lab.data import Bar
from hypothesis_lab.engine import ExecutionConfig
from hypothesis_lab.portfolio import portfolio_backtest

START = datetime(2024, 1, 1, tzinfo=UTC)


def at(second):
    return (START + timedelta(seconds=second)).isoformat()


def quote(symbol, second, bid=100, ask=100, size=100, **extra):
    return {
        "type": "quote",
        "instrument": symbol,
        "timestamp": at(second),
        "bid": bid,
        "ask": ask,
        "bid_size": size,
        "ask_size": size,
        **extra,
    }


def spec(symbol, kind="spot", **extra):
    return {"symbol": symbol, "kind": kind, **extra}


class PortfolioContracts(unittest.TestCase):
    def setUp(self):
        self.bars = [Bar(START + timedelta(minutes=i), 100, 101, 99, 100, 100) for i in range(5)]
        self.cfg = ExecutionConfig(
            initial_cash=1000, fee_bps=0, slippage_bps=0, bar_seconds=60, periods_per_year=525600
        )

    def run_book(self, specs, events, targets, **settings):
        intents = [None] * len(self.bars)
        for index, value in targets.items():
            intents[index] = {"targets": value}
        return portfolio_backtest(
            self.bars,
            intents,
            self.cfg,
            {
                "instruments": specs,
                "events": events,
                "participation_rate": 1,
                "max_quote_age_ms": 2000,
                **settings,
            },
        )

    def test_funding_vampire_shared_cash_and_same_time_funding_precedes_exit(self):
        instruments = [spec("S"), spec("P", "perpetual", allow_short=True)]
        events = [quote(symbol, time) for time in [59, 179, 239] for symbol in ["S", "P"]]
        events += [
            {
                "type": "funding",
                "instrument": "P",
                "timestamp": at(time),
                "mark_price": 100,
                "rate": 0.01,
            }
            for time in [120, 180]
        ]
        result = self.run_book(instruments, events, {0: {"S": 1, "P": -1}, 2: {"S": 0, "P": 0}})
        self.assertEqual(result["metrics"]["funding_cash"], 2)
        self.assertEqual(result["metrics"]["final_equity"], 1002)
        self.assertEqual(result["equity"][-1]["cash"], 1002)
        self.assertEqual(len(result["fills"]), 4)
        self.assertTrue(
            all(state["units"] == 0 for state in result["portfolio"]["final_positions"].values())
        )

    def test_long_perpetual_pays_funding_without_paying_notional(self):
        events = [
            quote("P", 59),
            {
                "type": "funding",
                "instrument": "P",
                "timestamp": at(120),
                "mark_price": 100,
                "rate": 0.01,
            },
        ]
        result = self.run_book([spec("P", "perpetual")], events, {0: {"P": 1}})
        self.assertEqual(result["equity"][0]["cash"], 1000)
        self.assertEqual(result["equity"][-1]["cash"], 999)
        self.assertEqual(result["metrics"]["funding_cash"], -1)

    def test_bid_ask_partial_displayed_liquidity_and_shadow_consumption(self):
        events = [
            quote("S", 59, bid=99, ask=101, size=2),
            quote("S", 89, bid=99, ask=101, size=2),
            quote("S", 119, bid=99, ask=101, size=4),
        ]
        result = self.run_book(
            [spec("S")], events, {0: {"S": 5}}, participation_rate=0.5, max_quote_age_ms=200000
        )
        self.assertEqual([f["units"] for f in result["fills"]], [1, 1])
        self.assertEqual(result["portfolio"]["final_positions"]["S"]["units"], 2)
        self.assertEqual(result["metrics"]["final_equity"], 996)

    def test_delayed_arrival_uses_current_quotes_inside_bar_not_next_daily_open(self):
        self.cfg = ExecutionConfig(
            initial_cash=1000, fee_bps=0, slippage_bps=0, bar_seconds=60, latency_ms=500
        )
        events = [quote("S", 59, 100, 100), quote("S", 60.25, 102, 102)]
        result = self.run_book([spec("S")], events, {0: {"S": 1}})
        self.assertEqual(result["fills"][0]["price"], 102)
        self.assertEqual(result["fills"][0]["filled_at"], at(60.5))

    def test_stale_quotes_and_oversized_collateral_are_not_filled(self):
        stale = self.run_book([spec("S")], [quote("S", 1)], {0: {"S": 1}})
        self.assertEqual(stale["fills"], [])
        large = self.run_book(
            [spec("P", "perpetual", allow_short=True)], [quote("P", 59)], {0: {"P": -11}}
        )
        self.assertEqual(large["fills"], [])
        self.assertEqual(
            large["orders"][0]["rejections"][0]["reason"], "insufficient_initial_collateral"
        )

    def test_dividend_entitlement_is_not_owned_by_same_time_buyer_and_pay_is_later(self):
        events = [
            quote("S", 59),
            quote("S", 119),
            {
                "type": "dividend",
                "instrument": "S",
                "timestamp": at(120),
                "amount": 2,
                "pay_at": at(210),
            },
        ]
        result = self.run_book([spec("S", "equity")], events, {0: {"S": 3}, 1: {"S": 5}})
        entitlement = next(f for f in result["cashflows"] if f["type"] == "dividend_entitlement")
        self.assertEqual(entitlement["held_units"], 3)
        self.assertEqual(entitlement["receivable"], 6)
        self.assertEqual(result["equity"][1]["dividends_receivable"], 6)
        self.assertEqual(result["metrics"]["dividend_cash"], 6)
        self.assertEqual(
            next(f for f in result["cashflows"] if f["type"] == "dividend_payment")["timestamp"],
            at(210),
        )

    def test_short_stock_requires_borrow_and_owes_dividend(self):
        events = [
            quote("S", 59),
            {"type": "dividend", "instrument": "S", "timestamp": at(120), "amount": 2},
        ]
        no = self.run_book([spec("S", "equity", allow_short=True)], events, {0: {"S": -2}})
        self.assertFalse(no["fills"])
        yes = self.run_book(
            [spec("S", "equity", allow_short=True, borrowable=True, borrow_rate_bps=0)],
            events,
            {0: {"S": -2}},
        )
        self.assertEqual(yes["metrics"]["dividend_cash"], -4)
        self.assertEqual(yes["metrics"]["final_equity"], 996)

    def test_option_premium_multiplier_and_cash_settlement(self):
        options = [spec("C", "option", right="call", strike=100, multiplier=100)]
        result = self.run_book(
            options,
            [
                quote("C", 59, 2, 2),
                {"type": "settlement", "instrument": "C", "timestamp": at(180), "price": 5},
            ],
            {0: {"C": 1}},
        )
        self.assertEqual(result["equity"][0]["cash"], 800)
        self.assertEqual(result["metrics"]["final_equity"], 1300)
        self.assertEqual(result["portfolio"]["final_positions"]["C"]["units"], 0)

    def test_short_option_requires_declared_margin_and_receives_premium(self):
        with self.assertRaisesRegex(ValueError, "margin per contract"):
            self.run_book(
                [spec("C", "option", right="call", strike=100, multiplier=100, allow_short=True)],
                [quote("C", 59, 2, 2)],
                {0: {"C": -1}},
            )
        result = self.run_book(
            [
                spec(
                    "C",
                    "option",
                    right="call",
                    strike=100,
                    multiplier=100,
                    allow_short=True,
                    short_margin_per_unit=500,
                )
            ],
            [
                quote("C", 59, 2, 2),
                {"type": "settlement", "instrument": "C", "timestamp": at(180), "price": 1},
            ],
            {0: {"C": -1}},
        )
        self.assertEqual(result["equity"][0]["cash"], 1200)
        self.assertEqual(result["metrics"]["final_equity"], 1100)

    def test_binary_settlement_and_max_loss_collateral(self):
        result = self.run_book(
            [spec("RAIN", "binary")],
            [
                quote("RAIN", 59, 0.4, 0.4),
                {"type": "settlement", "instrument": "RAIN", "timestamp": at(240), "price": 1},
            ],
            {0: {"RAIN": 10}},
        )
        self.assertEqual(result["metrics"]["final_equity"], 1006)
        with self.assertRaisesRegex(ValueError, "payout"):
            self.run_book(
                [spec("RAIN", "binary")], [quote("RAIN", 59, 0.4, 1.1)], {0: {"RAIN": 10}}
            )

    def test_american_assignment_delivers_stock_and_strike_cash(self):
        specs = [
            spec("S", "equity", allow_short=True, borrowable=True),
            spec(
                "C",
                "option",
                right="call",
                strike=100,
                multiplier=100,
                underlying="S",
                allow_short=True,
                short_margin_per_unit=500,
                exercise_style="american",
                settlement_type="physical",
            ),
        ]
        self.cfg = ExecutionConfig(initial_cash=20000, fee_bps=0, slippage_bps=0, bar_seconds=60)
        events = [
            quote("C", 59, 2, 2),
            quote("S", 59, 105, 105),
            {"type": "assignment", "instrument": "C", "timestamp": at(120), "quantity": 1},
        ]
        result = self.run_book(specs, events, {0: {"C": -1}})
        self.assertEqual(result["portfolio"]["final_positions"]["C"]["units"], 0)
        self.assertEqual(result["portfolio"]["final_positions"]["S"]["units"], -100)
        self.assertEqual(result["equity"][-1]["cash"], 30200)
        self.assertEqual(result["metrics"]["final_equity"], 19700)

    def test_maintenance_breach_attempts_only_observed_liquidation(self):
        events = [quote("P", 59, 100, 100), quote("P", 119, 10000, 10000, size=0.25)]
        result = self.run_book(
            [spec("P", "perpetual", allow_short=True)],
            events,
            {0: {"P": -1}},
            max_quote_age_ms=200000,
        )
        self.assertEqual(result["metrics"]["margin_calls"], 1)
        self.assertEqual(result["portfolio"]["final_positions"]["P"]["units"], -0.75)
        self.assertLess(result["metrics"]["final_equity"], 0)
        self.assertTrue(result["fills"][-1]["liquidation"])

    def test_future_quotes_do_not_change_prior_fills_and_output_is_exportable(self):
        events = [quote("S", 59), quote("S", 179, 100, 100)]
        result = self.run_book([spec("S")], events, {0: {"S": 1}})
        changed = copy.deepcopy(events)
        changed[-1].update(bid=1000, ask=1000)
        second = self.run_book([spec("S")], changed, {0: {"S": 1}})
        self.assertEqual(result["fills"], second["fills"])
        json.dumps(result, allow_nan=False)


class AdditionalExecutionContracts(unittest.TestCase):
    setUp = PortfolioContracts.setUp
    run_book = PortfolioContracts.run_book

    def test_partial_order_charges_one_ticket_fee_and_optional_per_fill_policy(self):
        self.cfg = ExecutionConfig(
            initial_cash=1000, fee_bps=0, fixed_fee=5, slippage_bps=0, bar_seconds=60
        )
        events = [quote("S", 59, size=2), quote("S", 119, size=4)]
        one = self.run_book([spec("S")], events, {0: {"S": 5}}, participation_rate=0.5)
        each = self.run_book(
            [spec("S")], events, {0: {"S": 5}}, participation_rate=0.5, fixed_fee_policy="per_fill"
        )
        self.assertEqual(one["metrics"]["fees_paid"], 5)
        self.assertEqual(each["metrics"]["fees_paid"], 10)

    def test_quote_receipt_delay_prevents_a_later_source_quote_becoming_known_early(self):
        self.cfg = ExecutionConfig(
            initial_cash=1000, fee_bps=0, slippage_bps=0, bar_seconds=60, data_delay_ms=500
        )
        result = self.run_book(
            [spec("S")], [quote("S", 59.5, 100, 100), quote("S", 60.25, 102, 102)], {0: {"S": 1}}
        )
        self.assertEqual(result["fills"][0]["filled_at"], at(60.5))
        self.assertEqual(result["fills"][0]["price"], 100)
