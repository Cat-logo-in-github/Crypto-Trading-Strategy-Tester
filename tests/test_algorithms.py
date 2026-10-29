import math
import unittest
from datetime import UTC, datetime, timedelta

from hypothesis_lab.algorithms import (
    SignalInterpreter,
    algorithm_decisions,
    apply_signals,
    plan_algorithm,
    signal_rows,
)
from hypothesis_lab.data import Bar
from hypothesis_lab.periods import select_period


class SignalTests(unittest.TestCase):
    def setUp(self):
        self.rows = [{"x": float(x), "y": float(5 - x)} for x in range(1, 6)]

    def test_hand_calculated_arithmetic_and_trailing_values(self):
        read = SignalInterpreter(self.rows).run
        self.assertEqual(read("mean(x, 3)"), [None, None, 2, 3, 4])
        self.assertEqual(read("sum(x, 2)"), [None, 3, 5, 7, 9])
        self.assertEqual(read("lag(x, 2)"), [None, None, 1, 2, 3])
        self.assertEqual(read("difference(x, 1)"), [None, 1, 1, 1, 1])
        self.assertEqual(read("count(x > 2, 2)"), [None, 0, 1, 2, 2])
        self.assertEqual(read("where(x > 2, x * 2, -x)"), [-1, -2, 6, 8, 10])
        self.assertAlmostEqual(read("zscore(x, 3)")[2], math.sqrt(1.5))

    def test_missing_values_never_become_measurements_or_truth(self):
        read = SignalInterpreter([{"x": 1}, {"x": None}, {"x": 3}]).run
        self.assertEqual(read("x / 0"), [None, None, None])
        self.assertEqual(read("mean(x, 2)"), [None, None, None])
        self.assertEqual(read("not (x > 0)"), [False, None, False])
        self.assertEqual(read("(x > 0) and False"), [False, False, False])
        self.assertEqual(read("(x > 0) or True"), [True, True, True])

    def test_prefix_causality_and_chained_signals(self):
        definitions = [
            {"name": "growth", "expression": "pct_change(x, 1)"},
            {"name": "signal", "expression": "growth > lag(growth, 1)"},
        ]
        full = apply_signals(self.rows, definitions)
        self.assertEqual(apply_signals(self.rows[:3], definitions), full[:3])
        self.assertEqual(full[1]["growth"], 1)
        self.assertFalse(full[2]["signal"])

    def test_geospatial_distances_and_crossing_events(self):
        read = SignalInterpreter(
            [{"lat": 0, "lon": 0}, {"lat": 0, "lon": 1}, {"lat": 0, "lon": 2}]
        ).run
        distance = read("distance_km(lat, lon, 0, 0)")
        self.assertEqual(distance[0], 0)
        self.assertAlmostEqual(distance[1], 111.195, places=2)
        self.assertEqual(read("inside_box(lat, lon, -1, 0.5, 1, 1.5)"), [False, True, False])
        self.assertEqual(read("crosses_above(lon, 0.5)"), [None, True, False])
        self.assertEqual(read("crosses_below(lon, 0.5)"), [None, False, False])

    def test_untrusted_code_future_windows_and_unknown_columns_are_rejected(self):
        for expression in [
            "__import__('os').system('whoami')",
            "open('x')",
            "x[-1]",
            "[x for x in y]",
            "(lambda: 1)()",
            "market.__class__",
            "unknown",
            "lag(x, -1)",
            "mean(x, True)",
            "sum(x, 1001)",
            "x ** 10000",
        ]:
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                SignalInterpreter(self.rows).run(expression)
        with self.assertRaises(ValueError):
            apply_signals(self.rows, [{"name": "x", "expression": "x + 1"}])

    def test_exit_priority_cash_sizing_and_missing_entry(self):
        rows = [{"a": None, "b": 0}, {"a": 1, "b": 0}, {"a": 1, "b": 1}]
        decisions, diagnostics = algorithm_decisions(
            rows, {"entry": "a > 0", "exit": "b > 0", "sizing": "cash", "amount": 50}
        )
        self.assertIsNone(decisions[0])
        self.assertEqual(decisions[1].buy_cash, 50)
        self.assertEqual(decisions[2].target_weight, 0)
        self.assertEqual(diagnostics["missing_entry_rows"], 1)

    def test_calendar_follows_delayed_decision_clock_and_reserves_names(self):
        bar = Bar(datetime(2024, 1, 31, 22, tzinfo=UTC), 10, 12, 9, 11, 10)
        self.assertEqual(signal_rows([bar], [{}], 3600)[0]["month_utc"], 1)
        delayed = signal_rows([bar], [{}], 3600, 7200)[0]
        self.assertEqual((delayed["month_utc"], delayed["hour_utc"]), (2, 1))
        with self.assertRaisesRegex(ValueError, "Rename measured fields"):
            signal_rows([bar], [{"hour_utc": 3}], 3600)

    def test_plan_retains_separate_entry_exit_and_unknown_ideas_need_definitions(self):
        plan = plan_algorithm(
            "Buy when ice cream sales > 100; sell when traffic count < 20",
            ["ice_cream_sales", "traffic_count"],
        )
        self.assertTrue(plan["executable"])
        self.assertIn("traffic_count", plan["draft"]["exit"])
        unknown = plan_algorithm(
            "Buy when a satellite passes New York and sell when it passes New Jersey",
            ["latitude", "longitude"],
        )
        self.assertFalse(unknown["executable"])
        self.assertTrue(unknown["clarifications"])


class PeriodTests(unittest.TestCase):
    def setUp(self):
        day = datetime(2024, 1, 1, tzinfo=UTC)
        self.bars = [Bar(day + timedelta(days=i), 10, 12, 9, 11, 10) for i in range(20)]

    def test_date_window_completed_bars_inclusive_end_and_warmup(self):
        selected, start, info = select_period(
            self.bars, {"start": "2024-01-10", "end": "2024-01-12"}, 86400
        )
        self.assertEqual(info["bars"], 3)
        self.assertEqual(start, 9)
        self.assertEqual(len(selected), 12)
        self.assertEqual(info["end"], "2024-01-13T00:00:00+00:00")
        rows = signal_rows(selected, [{} for _ in selected], 86400)
        self.assertEqual(SignalInterpreter(rows).run("mean(market.close, 10)")[start], 11)

    def test_duration_bounds_and_no_partial_bar(self):
        selected, start, info = select_period(
            self.bars, {"end": "2024-01-10T12:00:00Z", "last_bars": 3}, 86400
        )
        self.assertEqual(info["start"], "2024-01-07T00:00:00+00:00")
        self.assertEqual(selected[start].timestamp, self.bars[6].timestamp)
        for period in [
            {"last_bars": True},
            {"last_bars": 1},
            {"end": "2024-01-01"},
            {"start": "2024-01-10", "end": "2024-01-05"},
            {"duration": "fake"},
        ]:
            with self.subTest(period=period), self.assertRaises(ValueError):
                select_period(self.bars, period, 86400)
