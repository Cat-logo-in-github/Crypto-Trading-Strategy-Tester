"""Offline financial, timestamp and rule contracts with independent expectations."""

import math
import random
import statistics
import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone

from hypothesis_lab.data import (
    Bar,
    Event,
    available_value,
    fingerprint,
    fixtures,
    load_bars,
    load_events,
    timestamp,
    validate_bars,
)
from hypothesis_lab.engine import (
    Decision,
    ExecutionConfig,
    backtest,
    benchmark,
    calculate_metrics,
)
from hypothesis_lab.strategies import (
    decisions_for,
    evaluate_rule,
    feature,
    parse_hypothesis,
    preset,
    python_decisions,
    sma,
)

START = datetime(2024, 1, 1, tzinfo=UTC)


def bars_at(prices):
    """Daily flat bars; independent opening/closing prices are set in specific tests."""
    return [
        Bar(START + timedelta(days=i), price, price, price, price, 100)
        for i, price in enumerate(prices)
    ]


class ExecutionTests(unittest.TestCase):
    def test_fee_inclusive_cash_buy_uses_actual_slipped_next_open(self):
        bars = bars_at([50, 100, 110])
        config = ExecutionConfig(initial_cash=1000, fee_bps=100, slippage_bps=100)
        result = backtest(bars, [Decision(buy_cash=100), None, None], config)
        fill = result["fills"][0]
        # A $100 total budget buys at $101 and pays 1% of its notional.
        expected_units = 100 / 102.01
        self.assertAlmostEqual(fill["price"], 101)
        self.assertAlmostEqual(fill["quantity"], expected_units)
        self.assertAlmostEqual(fill["fee"], 100 / 101)
        self.assertAlmostEqual(result["equity"][-1]["cash"], 900)
        self.assertAlmostEqual(result["metrics"]["final_equity"], 900 + 110 * expected_units)
        self.assertAlmostEqual(
            result["metrics"]["total_return"], (900 + 110 * expected_units) / 1000 - 1
        )
        self.assertEqual(result["equity"][0]["equity"], 1000)
        self.assertEqual(result["equity"][0]["units"], 0)

    def test_roundtrips_allocate_entry_exit_costs_and_profit_factor(self):
        bars = bars_at([100, 100, 120, 100, 90, 90])
        decisions = [
            Decision(buy_cash=100),
            Decision(target_weight=0),
            Decision(buy_cash=100),
            Decision(target_weight=0),
            None,
            None,
        ]
        config = ExecutionConfig(initial_cash=1000, fee_bps=100, slippage_bps=100)
        result = backtest(bars, decisions, config)
        # Both entries spend exactly $100. Sales execute 1% below their opens,
        # and the fee removes another 1% of sale notional.
        winning_pnl = (100 / 102.01) * 117.612 - 100
        losing_pnl = (100 / 102.01) * 88.209 - 100
        self.assertGreater(winning_pnl, 0)
        self.assertLess(losing_pnl, 0)
        self.assertAlmostEqual(result["metrics"]["final_equity"], 1000 + winning_pnl + losing_pnl)
        self.assertAlmostEqual(result["metrics"]["profit_factor"], winning_pnl / -losing_pnl)
        self.assertEqual(result["metrics"]["closed_trade_count"], 2)
        self.assertEqual(result["metrics"]["trade_count"], 4)
        self.assertAlmostEqual(result["equity"][-1]["units"], 0)

    def test_target_weights_hold_after_costs_for_buys_and_sells(self):
        bars = bars_at([100, 100, 120, 80])
        decisions = [
            Decision(target_weight=0.5),
            Decision(target_weight=0.25),
            Decision(target_weight=0),
            None,
        ]
        result = backtest(
            bars, decisions, ExecutionConfig(initial_cash=1000, fee_bps=125, slippage_bps=75)
        )
        for index, expected_weight in ((1, 0.5), (2, 0.25), (3, 0)):
            row = result["equity"][index]
            actual = row["units"] * bars[index].close / row["equity"]
            self.assertAlmostEqual(actual, expected_weight)
        self.assertEqual([fill["side"] for fill in result["fills"]], ["buy", "sell", "sell"])

    def test_decision_clock_is_close_time_and_fill_waits_for_next_open(self):
        bars = [
            Bar(START, 10, 12, 10, 12),
            Bar(START + timedelta(hours=2), 30, 30, 30, 30),
        ]
        result = backtest(
            bars,
            [Decision(buy_cash=60), None],
            ExecutionConfig(initial_cash=100, fee_bps=0, slippage_bps=0, bar_seconds=3600),
        )
        fill = result["fills"][0]
        self.assertEqual(fill["decision_bar_open"], START.isoformat())
        self.assertEqual(fill["decision_at"], (START + timedelta(hours=1)).isoformat())
        self.assertEqual(fill["filled_at"], (START + timedelta(hours=2)).isoformat())
        self.assertEqual(fill["price"], 30)
        self.assertEqual(fill["quantity"], 2)
        self.assertEqual(result["equity"][0]["cash"], 100)
        self.assertTrue(any("gap" in warning.lower() for warning in result["warnings"]))

    def test_final_intent_expires_and_never_fabricates_a_fill(self):
        result = backtest(bars_at([100, 100]), [None, Decision(target_weight=1)])
        self.assertEqual(result["fills"], [])
        self.assertEqual(
            result["orders"],
            [{"submitted_bar": 1, "fill_bar": None, "status": "expired_end_of_data"}],
        )
        self.assertEqual(result["metrics"]["total_return"], 0)

    def test_benchmark_uses_same_clock_costs_and_initial_capital(self):
        bars = bars_at([90, 100, 125])
        config = ExecutionConfig(initial_cash=1000, fee_bps=100, slippage_bps=100)
        result = benchmark(bars, config)
        self.assertAlmostEqual(result["metrics"]["final_equity"], 1000 / 102.01 * 125)
        self.assertAlmostEqual(result["metrics"]["total_return"], 125 / 102.01 - 1)
        self.assertEqual(result, backtest(bars, decisions_for(bars, preset("buy_hold")), config))
        self.assertEqual(result["fills"][0]["filled_at"], bars[1].timestamp.isoformat())

    def test_invalid_intents_configuration_and_overlapping_bars(self):
        for kwargs in (
            {},
            {"target_weight": 0.5, "buy_cash": 100},
            {"target_weight": -1},
            {"target_weight": 1.01},
            {"buy_cash": 0},
            {"buy_cash": float("nan")},
        ):
            with self.subTest(intent=kwargs), self.assertRaises(ValueError):
                Decision(**kwargs)
        for kwargs in (
            {"initial_cash": 0},
            {"fee_bps": -1},
            {"slippage_bps": 10000},
            {"periods_per_year": 0},
            {"bar_seconds": 0},
            {"initial_cash": float("inf")},
        ):
            with self.subTest(configuration=kwargs), self.assertRaises(ValueError):
                ExecutionConfig(**kwargs)
        with self.assertRaises(ValueError):
            backtest(bars_at([100, 100]), [None])
        with self.assertRaises(ValueError):
            backtest(bars_at([100, 100]), [None, None], ExecutionConfig(bar_seconds=172800))

    def test_metrics_use_capital_peak_sample_volatility_and_undefined_cases(self):
        config = ExecutionConfig(initial_cash=100, periods_per_year=365)
        metrics = calculate_metrics([100, 120, 90, 99], config, [], [10, -5], bars_at([1, 1, 1, 1]))
        returns = [0.2, -0.25, 0.1]
        self.assertAlmostEqual(metrics["total_return"], -0.01)
        self.assertAlmostEqual(metrics["max_drawdown"], -0.25)
        self.assertAlmostEqual(
            metrics["annualized_volatility"], statistics.stdev(returns) * math.sqrt(365)
        )
        self.assertAlmostEqual(
            metrics["sharpe"], statistics.mean(returns) / statistics.stdev(returns) * math.sqrt(365)
        )
        self.assertEqual(metrics["profit_factor"], 2)
        self.assertIsNone(metrics["annualized_return"])
        empty = backtest(bars_at([1, 1, 1]), [None, None, None])["metrics"]
        self.assertIsNone(empty["sharpe"])
        self.assertIsNone(empty["profit_factor"])
        self.assertEqual(empty["annualized_volatility"], 0)

    def test_annualized_return_requires_a_year_of_elapsed_history(self):
        bars = bars_at([1, 1])
        bars[1] = replace(bars[1], timestamp=START + timedelta(days=730.485))
        metrics = calculate_metrics([100, 121], ExecutionConfig(initial_cash=100), [], [], bars)
        self.assertAlmostEqual(metrics["annualized_return"], 0.1)

    def test_seeded_accounting_paths_reconcile_fills_to_cash_units_and_equity(self):
        rng = random.Random(142)
        for trial in range(100):
            price, bars = 100.0, []
            for i in range(50):
                opening = price * math.exp(rng.uniform(-0.3, 0.3))
                price = opening * math.exp(rng.uniform(-0.2, 0.2))
                bars.append(
                    Bar(
                        START + timedelta(days=i),
                        opening,
                        max(price, opening),
                        min(price, opening),
                        price,
                    )
                )
            decisions = [
                None
                if rng.random() < 0.2
                else (
                    Decision(buy_cash=rng.uniform(0.01, 3000))
                    if rng.random() < 0.3
                    else Decision(target_weight=rng.random())
                )
                for _ in bars
            ]
            config = ExecutionConfig(
                initial_cash=1000, fee_bps=rng.uniform(0, 300), slippage_bps=rng.uniform(0, 300)
            )
            result = backtest(bars, decisions, config)
            cash, units = 1000.0, 0.0
            for fill in result["fills"]:
                sign = 1 if fill["side"] == "buy" else -1
                cash -= sign * fill["notional"] + fill["fee"]
                units += sign * fill["quantity"]
            with self.subTest(trial=trial):
                self.assertAlmostEqual(cash, result["equity"][-1]["cash"], places=7)
                self.assertAlmostEqual(units, result["equity"][-1]["units"], places=7)
                self.assertAlmostEqual(
                    cash + units * bars[-1].close, result["metrics"]["final_equity"], places=7
                )
                self.assertTrue(
                    all(row["cash"] >= 0 and row["units"] >= 0 for row in result["equity"])
                )
                self.assertEqual(result, backtest(bars, decisions, config))


class DataTests(unittest.TestCase):
    def test_offsets_normalize_to_utc_and_naive_time_is_rejected(self):
        self.assertEqual(timestamp("2024-01-01T04:00:00+04:00"), START)
        self.assertEqual(timestamp("2024-01-01T00:00:00Z"), START)
        bar = Bar(datetime(2024, 1, 1, 4, tzinfo=timezone(timedelta(hours=4))), 1, 1, 1, 1)
        self.assertEqual(bar.timestamp, START)
        with self.assertRaises(ValueError):
            timestamp("2024-01-01T00:00:00")

    def test_nonfinite_nonpositive_or_inconsistent_ohlc_is_rejected(self):
        for kwargs in (
            {"close": float("nan")},
            {"open": float("inf")},
            {"low": 0},
            {"volume": -1},
            {"high": 9},
            {"low": 11},
        ):
            values = {
                "timestamp": START,
                "open": 10,
                "high": 10,
                "low": 10,
                "close": 10,
                "volume": 0,
            }
            values.update(kwargs)
            with self.subTest(values=kwargs), self.assertRaises(ValueError):
                Bar(**values)

    def test_market_csv_schema_duplicates_order_and_minimum_length(self):
        csv = "timestamp,open,high,low,close\n2024-01-01T00:00:00Z,1,1,1,1\n2024-01-02T00:00:00Z,2,2,2,2\n"
        bars = load_bars(csv, content=True)
        self.assertEqual([bar.close for bar in bars], [1, 2])
        self.assertEqual(bars[0].volume, 0)
        with self.assertRaises(ValueError):
            load_bars("timestamp,close\n2024-01-01T00:00:00Z,1", content=True)
        for sequence in (bars[:1], [bars[0], bars[0]], list(reversed(bars))):
            with self.subTest(sequence=sequence), self.assertRaises(ValueError):
                validate_bars(sequence)

    def test_events_wait_for_publication_then_revise_without_overwriting_history(self):
        events = [
            Event(START, START + timedelta(hours=2), 10, location="Town"),
            Event(START, START + timedelta(days=1), -5, location="Town"),
        ]
        self.assertIsNone(available_value(events, START + timedelta(hours=1)))
        self.assertEqual(available_value(events, START + timedelta(hours=3)), 10)
        self.assertEqual(available_value(events, START + timedelta(days=1, seconds=-1)), 10)
        self.assertEqual(available_value(events, START + timedelta(days=1)), -5)
        # A later publication revising an old observation cannot replace a newer observation.
        events += [
            Event(
                START + timedelta(days=1), START + timedelta(days=1, hours=2), 7, location="Town"
            ),
            Event(START, START + timedelta(days=2), -100, location="Town"),
        ]
        self.assertEqual(available_value(events, START + timedelta(days=2)), 7)
        self.assertIsNone(available_value(events, START + timedelta(days=4)))
        self.assertEqual(available_value(events, START + timedelta(days=3), max_age_hours=48), 7)

    def test_event_csv_duplicate_revisions_and_invalid_availability(self):
        header = "observed_at,available_at,value,field,location\n"
        row = "2024-01-01T00:00:00Z,2024-01-01T02:00:00Z,4,temperature,Town\n"
        events = load_events(header + row, content=True)
        self.assertEqual(events[0].value, 4)
        with self.assertRaises(ValueError):
            load_events(header + row + row.replace(",4,", ",5,"), content=True)
        with self.assertRaises(ValueError):
            Event(START, START - timedelta(seconds=1), 1)
        with self.assertRaises(ValueError):
            Event(START, START, float("nan"))

    def test_dataset_identity_is_deterministic_and_includes_revisions(self):
        bars = bars_at([1, 2])
        first = [Event(START, START, 4)]
        revised = first + [Event(START, START + timedelta(hours=1), 5)]
        self.assertEqual(fingerprint(bars, first), fingerprint(bars[:], first[:]))
        self.assertNotEqual(fingerprint(bars, first), fingerprint(bars, revised))
        self.assertNotEqual(
            fingerprint(bars), fingerprint([bars[0], replace(bars[1], close=1.5, low=1.5)])
        )


class StrategyTests(unittest.TestCase):
    def test_supported_parser_preserves_full_weather_specification(self):
        sentence = "Buy $100 of Bitcoin whenever the temperature in this town falls below 5°C, provided Bitcoin is above its 200-day moving average."
        spec = parse_hypothesis(sentence)
        self.assertEqual(spec, preset("weather", amount=100, threshold=5, slow=200))
        self.assertEqual(parse_hypothesis(sentence), spec)
        self.assertEqual(
            parse_hypothesis("Buy BTC when 10-day SMA is above 20-day SMA"),
            preset("sma_cross", fast=10, slow=20),
        )
        self.assertEqual(parse_hypothesis("buy and hold btc"), preset("buy_hold"))

    def test_parser_rejects_partial_matches_and_unsupported_ideas(self):
        for sentence in (
            "Buy and hold BTC unless volatility is high",
            "Buy BTC when 10-day SMA is above 20-day SMA and sell before earnings",
            "Buy when satellites pass overhead",
            "Buy $0 of Bitcoin whenever temperature drops below 5C when BTC is above its 2-day moving average",
        ):
            with self.subTest(sentence=sentence), self.assertRaises(ValueError):
                parse_hypothesis(sentence)

    def test_rule_trees_evaluate_and_or_missing_warmup_and_bound_depth(self):
        bars = bars_at([10, 12])
        true_rule = {"left": "close", "op": ">", "right": 11}
        false_rule = {"left": "close", "op": "<", "right": 11}
        self.assertFalse(evaluate_rule({"all": [true_rule, false_rule]}, bars, 1, [], {}))
        self.assertTrue(evaluate_rule({"any": [true_rule, false_rule]}, bars, 1, [], {}))
        self.assertTrue(
            evaluate_rule({"all": [true_rule, {"any": [true_rule, false_rule]}]}, bars, 1, [], {})
        )
        self.assertFalse(evaluate_rule({"left": "sma_3", "op": ">", "right": 1}, bars, 1, [], {}))
        for rule in (
            {"all": []},
            {"left": "close", "op": "!=", "right": 0},
            {"left": "close", "op": ">", "right": float("nan")},
        ):
            with self.subTest(rule=rule), self.assertRaises(ValueError):
                evaluate_rule(rule, bars, 1, [], {})
        deep = true_rule
        for _ in range(10):
            deep = {"all": [deep]}
        with self.assertRaises(ValueError):
            evaluate_rule(deep, bars, 1, [], {})

    def test_indicator_warmup_hand_values_and_prefix_causality(self):
        self.assertIsNone(sma([1, 2], 3))
        self.assertEqual(sma([1, 2, 3, 4], 3), 3)
        bars = bars_at([10, 11, 12, 15, 999])
        for index in range(4):
            for name in ("close", "sma_3", "momentum_2"):
                self.assertEqual(
                    feature(name, bars, index, [], {}),
                    feature(name, bars[: index + 1], index, [], {}),
                )
        self.assertAlmostEqual(feature("momentum_2", bars, 3, [], {}), 15 / 11 - 1)
        self.assertIsNone(feature("momentum_2", bars, 1, [], {}))
        with self.assertRaises(ValueError):
            sma([1], 0)

    def test_python_extension_receives_immutable_history_prefix_only(self):
        testcase = self
        seen = []

        class InspectingStrategy:
            def decide(self, history):
                testcase.assertIsInstance(history, tuple)
                testcase.assertEqual(len(history), len(seen) + 1)
                testcase.assertEqual(history[0].timestamp, START)
                with testcase.assertRaises(FrozenInstanceError):
                    history[0].close = 999
                seen.append(history[-1].timestamp)
                return Decision(target_weight=0.5)

        bars = bars_at([1, 2, 3])
        decisions = python_decisions(bars, InspectingStrategy())
        self.assertEqual(seen, [bar.timestamp for bar in bars])
        self.assertEqual(bars[0].close, 1)
        self.assertEqual(len(decisions), 3)

    def test_multiple_event_locations_require_explicit_selection(self):
        bars = bars_at([10, 12])
        events = [
            Event(START, START, 1, location="Town A"),
            Event(START, START, 10, location="Town B"),
        ]
        spec = preset("weather", slow=2)
        with self.assertRaisesRegex(ValueError, "location"):
            decisions_for(bars, spec, events)
        spec["location"] = "Town A"
        self.assertIsNotNone(decisions_for(bars, spec, events)[1])
        spec["location"] = "Town B"
        self.assertIsNone(decisions_for(bars, spec, events)[1])

    def test_complete_weather_sma_experiment_has_hand_calculated_fills(self):
        bars = bars_at([10, 12, 14, 16, 18])
        # Observation occurs mid Jan 2 but is published at Jan 3 midnight.
        # It expires after 48 hours, allowing exactly the Jan 2 and Jan 3 closes.
        event = Event(
            START + timedelta(days=1, hours=12), START + timedelta(days=2), 0, location="Town"
        )
        spec = preset("weather", slow=2, amount=100)
        spec["location"] = "Town"
        decisions = decisions_for(bars, spec, [event])
        self.assertEqual([i for i, value in enumerate(decisions) if value is not None], [1, 2])
        result = backtest(
            bars, decisions, ExecutionConfig(initial_cash=500, fee_bps=0, slippage_bps=0)
        )
        self.assertEqual([fill["price"] for fill in result["fills"]], [14, 16])
        self.assertEqual(result["metrics"]["trade_count"], 2)
        self.assertAlmostEqual(result["equity"][-1]["cash"], 300)
        self.assertAlmostEqual(result["metrics"]["final_equity"], 300 + 18 * (100 / 14 + 100 / 16))

    def test_bundled_weather_200_day_example_is_offline_and_causal(self):
        bars, events = fixtures()
        spec = parse_hypothesis(
            "Buy $100 of Bitcoin whenever temperature drops below 5C when BTC is above its 200-day moving average"
        )
        decisions = decisions_for(bars, spec, events)
        self.assertTrue(all(decision is None for decision in decisions[:199]))
        self.assertTrue(any(decision is not None for decision in decisions[199:-1]))
        result = backtest(bars, decisions, ExecutionConfig())
        self.assertGreater(result["metrics"]["trade_count"], 0)
        for fill in result["fills"]:
            self.assertGreaterEqual(timestamp(fill["filled_at"]), timestamp(fill["decision_at"]))
        self.assertEqual(
            result, backtest(bars, decisions_for(bars, spec, events), ExecutionConfig())
        )


if __name__ == "__main__":
    unittest.main()
