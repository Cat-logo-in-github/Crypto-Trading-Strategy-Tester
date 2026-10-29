"""Independent hand expectations for execution clocks, costs and portfolio identities."""

import json
import math
import random
import unittest
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from hypothesis_lab.costs import execution_profiles
from hypothesis_lab.data import Bar, Event, load_bars, load_events, timestamp
from hypothesis_lab.engine import Decision, ExecutionConfig, backtest, benchmark
from hypothesis_lab.strategies import decisions_for, feature, preset, sma

START = datetime(2026, 1, 1, tzinfo=UTC)


def second_bars(prices):
    return [
        Bar(START + timedelta(seconds=i), price, price, price, price, 100)
        for i, price in enumerate(prices)
    ]


def no_costs(**changes):
    return ExecutionConfig(initial_cash=1000, fee_bps=0, slippage_bps=0, bar_seconds=1, **changes)


class TimingAuditTests(unittest.TestCase):
    def test_positive_latency_changes_price_and_cash_clock_not_just_a_timestamp(self):
        bars = second_bars([100, 200, 400, 800])
        result = backtest(bars, [Decision(buy_cash=100), None, None, None], no_costs(latency_ms=1))
        fill = result["fills"][0]
        self.assertEqual(fill["filled_at"], (START + timedelta(seconds=2)).isoformat())
        self.assertEqual(fill["price"], 400)
        self.assertEqual(fill["quantity"], 0.25)
        self.assertEqual(result["equity"][1]["cash"], 1000)
        self.assertEqual(result["equity"][1]["units"], 0)
        self.assertEqual(result["metrics"]["final_equity"], 1100)
        self.assertEqual(
            fill["eligible_at"], (START + timedelta(seconds=1, milliseconds=1)).isoformat()
        )

    def test_explicit_inference_availability_and_configured_delays_are_not_double_counted(self):
        bars = second_bars([100, 100, 200, 300, 400])
        decision = Decision(
            buy_cash=300, available_at=START + timedelta(seconds=2, milliseconds=200)
        )
        result = backtest(
            bars, [decision, None, None, None, None], no_costs(data_delay_ms=250, latency_ms=100)
        )
        fill = result["fills"][0]
        self.assertEqual(
            fill["market_available_at"],
            (START + timedelta(seconds=1, milliseconds=250)).isoformat(),
        )
        self.assertEqual(
            fill["decision_at"], (START + timedelta(seconds=2, milliseconds=200)).isoformat()
        )
        self.assertEqual(
            fill["eligible_at"], (START + timedelta(seconds=2, milliseconds=300)).isoformat()
        )
        self.assertEqual(fill["price"], 300)
        self.assertEqual(fill["quantity"], 1)
        self.assertIsInstance(json.loads(json.dumps(asdict(decision)))["available_at"], str)

    def test_exact_open_is_eligible_and_positive_submicrosecond_delay_never_disappears(self):
        bars = second_bars([100, 200, 300])
        decisions = [Decision(buy_cash=100), None, None]
        exact = backtest(bars, decisions, no_costs(latency_ms=1000))
        self.assertEqual(exact["fills"][0]["fill_bar"], 2)
        tiny = backtest(bars, decisions, no_costs(latency_ms=0.0001))
        self.assertEqual(tiny["fills"][0]["fill_bar"], 2)
        self.assertEqual(
            tiny["fills"][0]["eligible_at"],
            (START + timedelta(seconds=1, microseconds=1)).isoformat(),
        )

    def test_declared_early_readiness_cannot_trade_unpublished_close(self):
        bars = second_bars([100, 200, 300])
        result = backtest(
            bars,
            [Decision(buy_cash=100, available_at=START), None, None],
            no_costs(data_delay_ms=1),
        )
        self.assertEqual(result["fills"][0]["fill_bar"], 2)
        self.assertGreater(
            timestamp(result["fills"][0]["decision_at"]), START + timedelta(seconds=1)
        )

    def test_delayed_accumulation_intents_are_retained_and_processed_in_ready_order(self):
        bars = second_bars([10] * 6)
        decisions = [
            Decision(buy_cash=100, available_at=START + timedelta(seconds=4)),
            Decision(buy_cash=100, available_at=START + timedelta(seconds=3)),
            Decision(buy_cash=100),
            None,
            None,
            None,
        ]
        result = backtest(bars, decisions, no_costs())
        self.assertEqual([fill["submitted_bar"] for fill in result["fills"]], [1, 2, 0])
        self.assertEqual([fill["fill_bar"] for fill in result["fills"]], [3, 3, 4])
        self.assertEqual(result["equity"][-1]["cash"], 700)
        self.assertEqual(result["equity"][-1]["units"], 30)

    def test_latency_beyond_remaining_data_expires_without_cash_or_position_change(self):
        result = backtest(
            second_bars([10, 20, 30]),
            [Decision(target_weight=1), None, None],
            no_costs(latency_ms=5000),
        )
        self.assertEqual(result["fills"], [])
        self.assertEqual(result["orders"][0]["status"], "expired_end_of_data")
        self.assertEqual(result["metrics"]["final_equity"], 1000)
        self.assertIsNone(result["order_events"][0]["filled_at"])

    def test_window_retains_indicator_warmup_but_ignores_prior_intents(self):
        bars = second_bars([10, 10, 10, 20, 30, 40])
        decisions = [
            Decision(target_weight=1),
            None,
            Decision(buy_cash=100),
            Decision(target_weight=0),
            Decision(buy_cash=100),
            None,
        ]
        result = backtest(bars, decisions, no_costs(), start_index=2, end_index=5)
        self.assertEqual(len(result["equity"]), 3)
        self.assertEqual(result["equity"][0]["cash"], 1000)
        self.assertEqual([fill["fill_bar"] for fill in result["fills"]], [3, 4])
        self.assertEqual(result["window"]["pre_window_intents_ignored"], 1)
        self.assertEqual(result["orders"][-1]["status"], "expired_end_of_data")
        self.assertEqual(result["metrics"]["final_equity"], 1050)
        baseline = benchmark(bars, no_costs(), start_index=2, end_index=5)
        self.assertEqual(baseline["fills"][0]["submitted_bar"], 2)
        self.assertEqual(baseline["fills"][0]["fill_bar"], 3)
        self.assertEqual(baseline["window"]["first_bar_open"], result["window"]["first_bar_open"])

    def test_one_shot_rule_resets_at_active_window_and_keeps_prior_indicator_history(self):
        bars = second_bars([10, 20, 30, 40, 50])
        spec = {
            **preset("buy_hold"),
            "bar_seconds": 1,
            "entry": {"left": "sma_3", "op": ">", "right": 0},
        }
        decisions = decisions_for(bars, spec, start_index=2, end_index=5)
        self.assertEqual(decisions[:2], [None, None])
        self.assertIsNotNone(decisions[2])
        self.assertEqual(decisions[3:], [None, None])
        result = backtest(bars, decisions, no_costs(), start_index=2, end_index=5)
        self.assertEqual(result["fills"][0]["fill_bar"], 3)


class CostAccountingAuditTests(unittest.TestCase):
    def test_cash_budget_includes_fixed_commission_full_spread_and_slippage(self):
        config = ExecutionConfig(
            initial_cash=1000, fee_bps=100, fixed_fee=1, spread_bps=100, slippage_bps=50
        )
        bars = [Bar(START + timedelta(days=i), 100, 100, 100, 100) for i in range(3)]
        result = backtest(bars, [Decision(buy_cash=100), Decision(target_weight=0), None], config)
        buy, sell = result["fills"]
        quantity = 99 / 102.01
        self.assertAlmostEqual(buy["quantity"], quantity)
        self.assertAlmostEqual(buy["price"], 101)
        self.assertAlmostEqual(buy["fee"], quantity * 101 * 0.01 + 1)
        self.assertAlmostEqual(buy["spread_cost"], quantity * 0.5)
        self.assertAlmostEqual(buy["slippage_cost"], quantity * 0.5)
        self.assertAlmostEqual(result["equity"][1]["cash"], 900)
        expected_sale_cash = quantity * 99 * 0.99 - 1
        self.assertAlmostEqual(sell["price"], 99)
        self.assertAlmostEqual(result["metrics"]["final_equity"], 900 + expected_sale_cash)
        self.assertAlmostEqual(sell["realized_pnl"], expected_sale_cash - 100)
        self.assertEqual(result["metrics"]["fixed_fees_paid"], 2)

    def test_target_weights_are_post_all_costs_for_buy_and_partial_sell(self):
        bars = [
            Bar(START + timedelta(days=i), price, price, price, price)
            for i, price in enumerate([100, 100, 120, 80])
        ]
        config = ExecutionConfig(
            initial_cash=1000, fee_bps=40, fixed_fee=2, spread_bps=30, slippage_bps=10
        )
        result = backtest(
            bars,
            [
                Decision(target_weight=0.5),
                Decision(target_weight=0.25),
                Decision(target_weight=0),
                None,
            ],
            config,
        )
        for index, target in [(1, 0.5), (2, 0.25), (3, 0)]:
            row = result["equity"][index]
            self.assertAlmostEqual(row["position_value"] / row["equity"], target)
        self.assertEqual([fill["side"] for fill in result["fills"]], ["buy", "sell", "sell"])

    def test_unchanged_target_never_charges_another_fixed_fee(self):
        result = backtest(
            second_bars([100] * 3),
            [Decision(target_weight=0.5), Decision(target_weight=0.5), None],
            no_costs(fixed_fee=2),
        )
        self.assertEqual(len(result["fills"]), 1)
        self.assertEqual(result["orders"][-1]["status"], "no_change")
        self.assertEqual(result["metrics"]["fixed_fees_paid"], 2)

    def test_insufficient_budget_for_fixed_cost_is_rejected_without_fee(self):
        result = backtest(
            second_bars([100, 100]), [Decision(buy_cash=1), None], no_costs(fixed_fee=2)
        )
        self.assertEqual(result["fills"], [])
        self.assertEqual(result["orders"][0]["status"], "rejected_insufficient_cash_for_costs")
        self.assertEqual(result["metrics"]["fees_paid"], 0)

    def test_sale_cannot_pay_a_fixed_fee_by_creating_negative_cash(self):
        config = ExecutionConfig(
            initial_cash=100, fee_bps=0, slippage_bps=0, fixed_fee=50, bar_seconds=1
        )
        result = backtest(
            second_bars([100, 100, 1]),
            [Decision(target_weight=1), Decision(target_weight=0), None],
            config,
        )
        self.assertEqual(len(result["fills"]), 1)
        self.assertEqual(result["orders"][-1]["status"], "rejected_insufficient_cash_for_costs")
        self.assertEqual(result["equity"][-1]["cash"], 0)
        self.assertEqual(result["equity"][-1]["units"], 0.5)
        self.assertEqual(result["metrics"]["fees_paid"], 50)

    def test_invalid_evaluation_bounds_never_silently_change_the_window(self):
        bars = second_bars([10] * 4)
        for start, end in [(-1, 3), (0, 5), (1, 2), (True, 4), (0, 3.5)]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                backtest(bars, [None] * 4, no_costs(), start_index=start, end_index=end)

    def test_valid_high_price_fractional_buy_is_not_lost_to_absolute_unit_cutoff(self):
        result = backtest(second_bars([1e12, 1e12]), [Decision(buy_cash=1), None], no_costs())
        self.assertEqual(len(result["fills"]), 1)
        self.assertEqual(result["fills"][0]["quantity"], 1e-12)
        self.assertAlmostEqual(result["equity"][-1]["cash"], 999)

    def test_total_equity_loss_has_defined_return_and_undefined_later_risk_ratios(self):
        result = backtest(
            second_bars([100] * 4),
            [Decision(target_weight=1), Decision(target_weight=0), None, None],
            ExecutionConfig(
                initial_cash=100, fee_bps=0, slippage_bps=0, fixed_fee=50, bar_seconds=1
            ),
        )
        self.assertEqual(result["metrics"]["total_return"], -1)
        self.assertEqual(result["metrics"]["max_drawdown"], -1)
        self.assertIsNone(result["metrics"]["sharpe"])
        self.assertIsNone(result["metrics"]["annualized_volatility"])

    def test_seeded_paths_reconcile_capital_and_all_cost_ledger_entries(self):
        rng = random.Random(721)
        for trial in range(25):
            bars = second_bars([100 * math.exp(rng.uniform(-0.5, 0.5)) for _ in range(40)])
            intents = [
                Decision(target_weight=rng.random())
                if rng.random() > 0.3
                else Decision(buy_cash=rng.uniform(1, 150))
                for _ in bars
            ]
            result = backtest(bars, intents, no_costs(fixed_fee=0.5, spread_bps=20, latency_ms=1))
            cash, units = 1000.0, 0.0
            for fill in result["fills"]:
                cash += (-fill["notional"] if fill["side"] == "buy" else fill["notional"]) - fill[
                    "fee"
                ]
                units += fill["quantity"] * (1 if fill["side"] == "buy" else -1)
                self.assertGreaterEqual(
                    timestamp(fill["filled_at"]), timestamp(fill["eligible_at"])
                )
            with self.subTest(trial=trial):
                self.assertAlmostEqual(cash, result["equity"][-1]["cash"], places=7)
                self.assertAlmostEqual(units, result["equity"][-1]["units"], places=7)
                for row in result["equity"]:
                    self.assertAlmostEqual(
                        row["equity"], 1000 + row["realized_pnl"] + row["unrealized_pnl"], places=7
                    )

    def test_cost_profiles_separate_commission_snapshots_from_latency_assumptions(self):
        profiles = execution_profiles()
        kraken = next(profile for profile in profiles if profile["id"] == "kraken_pro_tier1_2026")
        self.assertEqual(kraken["execution"]["fee_bps"], 80)
        self.assertEqual(kraken["fee_evidence"]["kind"], "official_schedule_snapshot")
        self.assertTrue(any("illustrative" in text.lower() for text in kraken["assumptions"]))
        for profile in profiles:
            ExecutionConfig(**profile["execution"])
        kraken["execution"]["fee_bps"] = 0
        self.assertEqual(
            next(profile for profile in execution_profiles() if profile["id"] == kraken["id"])[
                "execution"
            ]["fee_bps"],
            80,
        )


class InputAndRuleAuditTests(unittest.TestCase):
    def test_external_feature_cannot_shadow_market_close(self):
        bars = second_bars([100, 200])
        spec = {"_aligned_features": [{"close": 999}, {"close": 888}]}
        self.assertEqual(feature("close", bars, 0, [], spec), 100)
        self.assertEqual(feature("event:close", bars, 0, [], spec), 999)

    def test_external_publication_can_be_used_only_after_configured_data_delay(self):
        bars = second_bars([100, 100, 100])
        events = [Event(START, START + timedelta(seconds=1, milliseconds=50), 3)]
        spec = {
            **preset("weather", slow=1),
            "bar_seconds": 1,
            "entry": {"left": "temperature", "op": "<", "right": 5},
        }
        self.assertIsNone(decisions_for(bars, spec, events)[0])
        delayed = decisions_for(bars, {**spec, "data_delay_ms": 100}, events)
        self.assertIsNotNone(delayed[0])
        result = backtest(bars, delayed, no_costs())
        self.assertEqual(result["fills"][0]["fill_bar"], 2)

    def test_duplicate_csv_columns_and_boolean_prices_are_rejected(self):
        for csv, loader in [
            ("timestamp,open,open,high,low,close\n", load_bars),
            ("observed_at,available_at,value,value\n", load_events),
        ]:
            with self.subTest(csv=csv), self.assertRaises(ValueError):
                loader(csv, content=True)
        with self.assertRaises(ValueError):
            Bar(START, True, 1, 1, 1)
        with self.assertRaises(ValueError):
            timestamp(0)

    def test_cost_delay_bounds_and_explicit_availability_are_validated(self):
        for changes in [
            {"fixed_fee": -1},
            {"spread_bps": -1},
            {"spread_bps": 20000},
            {"latency_ms": -1},
            {"data_delay_ms": float("nan")},
            {"latency_ms": True},
        ]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                no_costs(**changes)
        with self.assertRaises(ValueError):
            Decision(buy_cash=1, available_at="2026-01-01T00:00:00")
        with self.assertRaises(ValueError):
            Decision(target_weight=True)
        self.assertEqual(sma([1e308, 1e308], 2), 1e308)


if __name__ == "__main__":
    unittest.main()
