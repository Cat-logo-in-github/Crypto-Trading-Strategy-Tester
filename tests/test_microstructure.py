"""Independent observed-book, queue, latency and cash reconciliation examples."""

import json
import math
import unittest
from datetime import UTC, datetime, timedelta

from hypothesis_lab.data import Bar
from hypothesis_lab.engine import Decision, ExecutionConfig
from hypothesis_lab.microstructure import (
    ReplayConfig,
    parse_replay,
    replay_backtest,
    replay_benchmark,
)

START = datetime(2026, 1, 1, tzinfo=UTC)
SYMBOL = "BTC/USD"


def stamp(seconds):
    return (START + timedelta(seconds=seconds)).isoformat()


def bars(count=5):
    return [Bar(START + timedelta(seconds=i), 100, 100, 100, 100, 100) for i in range(count)]


def quote(seconds, *, bid=99, ask=101, size=10, **extra):
    return {
        "timestamp": stamp(seconds),
        "instrument": SYMBOL,
        "type": "quote",
        "bid": bid,
        "ask": ask,
        "bid_size": size,
        "ask_size": size,
        **extra,
    }


def trade(seconds, quantity, *, price=100, aggressor="sell", **extra):
    return {
        "timestamp": stamp(seconds),
        "instrument": SYMBOL,
        "type": "trade",
        "price": price,
        "quantity": quantity,
        "aggressor": aggressor,
        **extra,
    }


def execution(**extra):
    return ExecutionConfig(
        **{
            "initial_cash": 1000,
            "fee_bps": 0,
            "slippage_bps": 0,
            "bar_seconds": 1,
            "latency_ms": 100,
            **extra,
        }
    )


def replay(**extra):
    return ReplayConfig(instrument=SYMBOL, participation_rate=1, **extra)


class ReplayParserTests(unittest.TestCase):
    def test_csv_ndjson_and_normalized_records_have_identical_content(self):
        event = quote(0.5)
        csv = (
            "timestamp,instrument,type,bid,ask,bid_size,ask_size\n"
            + f"{stamp(0.5)},BTC/USD,quote,99,101,10,10\n"
        )
        expected = parse_replay([event], instrument=SYMBOL)
        self.assertEqual(parse_replay(csv, "csv", instrument=SYMBOL), expected)
        self.assertEqual(parse_replay(json.dumps(event), "ndjson", instrument=SYMBOL), expected)
        self.assertEqual(parse_replay(expected, instrument=SYMBOL), expected)

    def test_instrument_units_crossed_quotes_duplicates_and_raw_delta_fields_are_rejected(self):
        invalid = [
            quote(0.5, instrument="ETH/USD"),
            quote(0.5, bid=102, ask=101),
            quote(0.5, bid_size=-1),
            {**quote(0.5), "update_id": 7},
            trade(0.5, True),
        ]
        for event in invalid:
            with self.subTest(event=event), self.assertRaises(ValueError):
                parse_replay([event], instrument=SYMBOL)
        with self.assertRaises(ValueError):
            parse_replay([quote(0.5), quote(0.5)], instrument=SYMBOL)
        with self.assertRaises(ValueError):
            parse_replay([quote(0.5, sequence=1), quote(0.5, sequence=1)], instrument=SYMBOL)

    def test_depth_is_absolute_bounded_and_duplicate_prices_are_rejected(self):
        event = {
            "timestamp": stamp(0.5),
            "type": "depth",
            "instrument": SYMBOL,
            "bids": [[98, 2], [99, 1]],
            "asks": [[102, 2], [101, 1]],
        }
        result = parse_replay([event], instrument=SYMBOL)[0]
        self.assertEqual(result["bids"], [[99, 1], [98, 2]])
        self.assertEqual(result["asks"], [[101, 1], [102, 2]])
        with self.assertRaises(ValueError):
            parse_replay([{**event, "asks": [[101, 1], [101, 2]]}], instrument=SYMBOL)


class AggressiveReplayTests(unittest.TestCase):
    def test_actual_bid_ask_spread_used_once_and_roundtrip_costs_reconcile(self):
        result = replay_backtest(
            bars(3),
            [Decision(buy_cash=101), Decision(target_weight=0), None],
            execution(spread_bps=1000),
            [quote(0.5), quote(1.5)],
            replay(),
        )
        self.assertEqual([fill["price"] for fill in result["fills"]], [101, 99])
        self.assertEqual([fill["quantity"] for fill in result["fills"]], [1, 1])
        self.assertEqual(result["metrics"]["final_equity"], 998)
        self.assertEqual(result["metrics"]["spread_cost"], 2)
        self.assertEqual(result["equity"][-1]["realized_pnl"], -2)
        self.assertEqual(result["fills"][0]["filled_at"], stamp(1.1))

    def test_depth_walk_cannot_exceed_fee_inclusive_cash_budget(self):
        depth = {
            "timestamp": stamp(0.5),
            "type": "depth",
            "instrument": SYMBOL,
            "bids": [[99, 10]],
            "asks": [[100, 0.5], [200, 10]],
        }
        result = replay_backtest(
            bars(),
            [Decision(buy_cash=100), None, None, None, None],
            execution(fixed_fee=1),
            [depth],
            replay(),
        )
        self.assertEqual([fill["price"] for fill in result["fills"]], [100, 200])
        self.assertAlmostEqual(sum(fill["notional"] + fill["fee"] for fill in result["fills"]), 100)
        self.assertAlmostEqual(result["equity"][-1]["cash"], 900)
        self.assertAlmostEqual(result["equity"][-1]["units"], 0.745)
        self.assertEqual(result["metrics"]["fixed_fees_paid"], 1)
        self.assertEqual(result["orders"][0]["status"], "partially_filled_ioc_canceled")

    def test_consumed_depth_is_not_replenished_by_an_unchanged_snapshot(self):
        result = replay_backtest(
            bars(4),
            [Decision(buy_cash=505), Decision(buy_cash=101), Decision(buy_cash=101), None],
            execution(),
            [quote(0.5, size=2), quote(1.5, size=2), quote(2.5, size=4)],
            ReplayConfig(instrument=SYMBOL, participation_rate=0.5),
        )
        self.assertEqual([fill["quantity"] for fill in result["fills"]], [1, 1])
        self.assertEqual([fill["submitted_bar"] for fill in result["fills"]], [0, 2])
        self.assertEqual(sum(fill["quantity"] for fill in result["fills"]), 2)

    def test_stale_and_future_same_time_quotes_cannot_fill_an_arrival(self):
        for observations in [[quote(0)], [quote(1.1)], [quote(1.2)]]:
            result = replay_backtest(
                bars(),
                [Decision(buy_cash=101), None, None, None, None],
                execution(),
                observations,
                replay(),
            )
            self.assertEqual(result["fills"], [])
            self.assertEqual(result["orders"][0]["status"], "rejected_missing_or_stale_quote")
        result = replay_backtest(
            bars(),
            [Decision(buy_cash=101), None, None, None, None],
            execution(),
            [quote(0.5), quote(1.1, bid=49, ask=50)],
            replay(),
        )
        self.assertEqual(result["fills"][0]["price"], 101)

    def test_explicit_delayed_availability_and_source_delay_control_readiness(self):
        cfg = ExecutionConfig(
            initial_cash=1000,
            fee_bps=0,
            slippage_bps=0,
            bar_seconds=1,
            data_delay_ms=20,
            latency_ms=50,
        )
        result = replay_backtest(
            bars(),
            [Decision(buy_cash=101), None, None, None, None],
            cfg,
            [quote(0.5), quote(1.05, bid=49, ask=50, available_at=stamp(1.15))],
            replay(),
        )
        self.assertEqual(result["fills"][0]["price"], 101)
        self.assertEqual(result["fills"][0]["eligible_at"], stamp(1.07))

    def test_quantity_step_min_notional_and_high_price_fractional_fill(self):
        result = replay_backtest(
            bars(),
            [Decision(buy_cash=55), None, None, None, None],
            execution(),
            [quote(0.5)],
            replay(quantity_step=0.1, min_notional=50),
        )
        self.assertEqual(result["fills"][0]["quantity"], 0.5)
        rejected = replay_backtest(
            bars(),
            [Decision(buy_cash=49), None, None, None, None],
            execution(),
            [quote(0.5)],
            replay(quantity_step=0.1, min_notional=50),
        )
        self.assertEqual(rejected["fills"], [])
        tiny = replay_backtest(
            bars(),
            [Decision(buy_cash=1), None, None, None, None],
            execution(),
            [quote(0.5, bid=1e12 - 1, ask=1e12)],
            replay(),
        )
        self.assertEqual(tiny["fills"][0]["quantity"], 1e-12)


class PassiveReplayTests(unittest.TestCase):
    def test_queue_ahead_and_trade_volume_are_consumed_once_with_partial_fills(self):
        intent = {
            "order_type": "limit",
            "side": "buy",
            "quantity": 2,
            "limit_price": 100,
            "client_id": "L1",
        }
        observations = [
            quote(0.5, bid=100, ask=101, size=2),
            trade(1.2, 1),
            trade(1.3, 2),
            trade(1.4, 1),
        ]
        result = replay_backtest(
            bars(),
            [intent, None, None, None, None],
            execution(fixed_fee=1, fee_bps=20),
            observations,
            replay(maker_fee_bps=2),
        )
        self.assertEqual([fill["quantity"] for fill in result["fills"]], [1, 1])
        self.assertEqual([fill["filled_at"] for fill in result["fills"]], [stamp(1.3), stamp(1.4)])
        self.assertAlmostEqual(result["metrics"]["fees_paid"], 1.04)
        self.assertEqual(result["metrics"]["fixed_fees_paid"], 1)
        self.assertTrue(
            all(fill["liquidity_role"] == "maker_assumption" for fill in result["fills"])
        )
        self.assertEqual(result["orders"][0]["status"], "filled")

    def test_cancel_and_ttl_win_over_ambiguous_same_time_trade_evidence(self):
        limit = {
            "order_type": "limit",
            "side": "buy",
            "quantity": 1,
            "limit_price": 100,
            "client_id": "L1",
        }
        records = [quote(0.5, bid=100), quote(1.5, bid=100), trade(2.1, 100)]
        canceled = replay_backtest(
            bars(), [limit, {"cancel_id": "L1"}, None, None, None], execution(), records, replay()
        )
        self.assertEqual(canceled["fills"], [])
        self.assertEqual(
            next(order for order in canceled["orders"] if order["id"] == "L1")["status"], "canceled"
        )
        expired = replay_backtest(
            bars(),
            [{**limit, "ttl_ms": 500}, None, None, None, None],
            execution(),
            [quote(0.5, bid=100), trade(1.6, 100)],
            replay(),
        )
        self.assertEqual(expired["fills"], [])
        self.assertEqual(expired["orders"][0]["status"], "expired_ttl")

    def test_unknown_side_or_trade_before_order_cannot_prove_a_passive_fill(self):
        limit = {
            "order_type": "limit",
            "side": "buy",
            "quantity": 1,
            "limit_price": 100,
            "client_id": "L1",
        }
        records = [quote(0.5, bid=100), trade(1.1, 100), trade(1.2, 100, aggressor="unknown")]
        result = replay_backtest(
            bars(),
            [limit, None, None, None, None],
            execution(),
            records,
            replay(queue_ahead_multiplier=0),
        )
        self.assertEqual(result["fills"], [])

    def test_resting_orders_reserve_cash_and_delayed_evidence_is_not_backdated(self):
        first = {
            "order_type": "limit",
            "side": "buy",
            "quantity": 8,
            "limit_price": 100,
            "client_id": "A",
        }
        second = {
            "order_type": "limit",
            "side": "buy",
            "quantity": 8,
            "limit_price": 100,
            "client_id": "B",
        }
        result = replay_backtest(
            bars(),
            [first, second, None, None, None],
            execution(),
            [quote(0.5, bid=100), quote(1.5, bid=100), trade(2.2, 20)],
            replay(queue_ahead_multiplier=0),
        )
        self.assertAlmostEqual(result["equity"][-1]["units"], 10)
        self.assertGreaterEqual(result["equity"][-1]["cash"], 0)
        delayed = replay_backtest(
            bars(),
            [{**first, "quantity": 1}, None, None, None, None],
            execution(),
            [quote(0.5, bid=100), quote(1.5, bid=100), trade(1.2, 1, available_at=stamp(2.2))],
            replay(queue_ahead_multiplier=0),
        )
        self.assertEqual(delayed["fills"][0]["filled_at"], stamp(2.2))
        self.assertEqual(delayed["equity"][1]["units"], 0)
        self.assertEqual(delayed["equity"][2]["units"], 1)


class ReplayLedgerTests(unittest.TestCase):
    def test_each_mark_and_fill_reconciles_capital_and_same_window_benchmark(self):
        market = bars(30)
        records = [
            quote(i + 0.5, bid=99 + math.sin(i), ask=101 + math.sin(i), size=10) for i in range(30)
        ]
        decisions = [Decision(target_weight=0.75 if i % 3 else 0.25) for i in range(30)]
        result = replay_backtest(
            market,
            decisions,
            execution(fixed_fee=0.1),
            records,
            replay(),
            start_index=3,
            end_index=25,
        )
        cash, units = 1000.0, 0.0
        for fill in result["fills"]:
            cash += (-fill["notional"] if fill["side"] == "buy" else fill["notional"]) - fill["fee"]
            units += fill["quantity"] * (1 if fill["side"] == "buy" else -1)
        self.assertAlmostEqual(cash, result["equity"][-1]["cash"])
        self.assertAlmostEqual(units, result["equity"][-1]["units"])
        for row in result["equity"]:
            self.assertAlmostEqual(
                row["equity"], 1000 + row["realized_pnl"] + row["unrealized_pnl"]
            )
        baseline = replay_benchmark(
            market, execution(fixed_fee=0.1), records, replay(), start_index=3, end_index=25
        )
        self.assertEqual(baseline["window"], result["window"])
        self.assertEqual(len(result["equity"]), 22)
        self.assertEqual(baseline["config"], result["config"])


if __name__ == "__main__":
    unittest.main()
