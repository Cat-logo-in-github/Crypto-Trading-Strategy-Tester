"""Small, offline checks of experimental RL transition semantics."""

import json
import math
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from hypothesis_lab.data import Bar
from hypothesis_lab.engine import Decision, ExecutionConfig, backtest
from hypothesis_lab.rl import ResearchEnv, policy_action, run_rl


def market(count=100):
    rows, previous = [], 100.0
    for index in range(count):
        close = 100 + index * 0.05 + 3 * math.sin(index / 4)
        rows.append(
            Bar(
                timestamp=datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=index),
                open=previous,
                high=max(previous, close) + 1,
                low=min(previous, close) - 1,
                close=close,
                volume=1000,
            )
        )
        previous = close
    return rows


class RLTests(unittest.TestCase):
    def test_hand_calculated_transition_reward_and_next_open_sale(self):
        bars = [
            Bar(datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=i), 100, 100, 100, 100)
            for i in range(10)
        ]
        bars.extend(
            [
                Bar(datetime(2020, 1, 11, tzinfo=UTC), 100, 110, 100, 110),
                Bar(datetime(2020, 1, 12, tzinfo=UTC), 120, 120, 110, 110),
            ]
        )
        env = ResearchEnv(bars, ExecutionConfig(initial_cash=1000, fee_bps=0, slippage_bps=0))
        observation, _ = env.reset()
        self.assertEqual(observation, [0, 0, 1, 0])
        _, reward, done, info = env.step(1)
        self.assertFalse(done)
        self.assertAlmostEqual(info["equity"], 1100)
        self.assertAlmostEqual(reward, math.log(1.1))
        self.assertEqual(env.result()["fills"][0]["filled_at"], bars[10].timestamp.isoformat())
        _, reward, done, info = env.step(0)
        self.assertTrue(done)
        self.assertAlmostEqual(info["equity"], 1200)
        self.assertAlmostEqual(info["cash"], 1200)
        self.assertAlmostEqual(reward, math.log(1200 / 1100))

    def test_environment_matches_common_engine_with_fees(self):
        bars = market(12)
        config = ExecutionConfig(initial_cash=1000, fee_bps=100, slippage_bps=100)
        env = ResearchEnv(bars, config)
        env.step(1)
        _, _, done, info = env.step(0)
        expected = backtest(
            bars[9:], [Decision(target_weight=1), Decision(target_weight=0), None], config
        )
        self.assertTrue(done)
        self.assertEqual(env.result(), expected)
        self.assertGreater(expected["metrics"]["fees_paid"], 0)
        self.assertGreaterEqual(info["cash"], 0)
        self.assertEqual(info["units"], 0)
        with self.assertRaises(ValueError):
            env.step(1)
        env.reset()
        for action in (True, -1, 2, 0.5):
            with self.subTest(action=action), self.assertRaises(ValueError):
                env.step(action)

    def test_observations_only_use_current_and_preceding_history(self):
        bars = market()
        changed = bars[:11] + [
            replace(bar, open=bar.open * 2, high=bar.high * 2, low=bar.low * 2, close=bar.close * 2)
            for bar in bars[11:]
        ]
        original_env, changed_env = ResearchEnv(bars), ResearchEnv(changed)
        self.assertEqual(original_env.reset(), changed_env.reset())
        self.assertEqual(original_env.step(1), changed_env.step(1))

    def test_training_is_seeded_and_does_not_use_held_out_period(self):
        bars = market()
        config = {"episodes": 2, "seed": 7}
        original = run_rl(bars, config)
        repeated = run_rl(bars, config)
        self.assertEqual(original, repeated)
        changed = bars[:80] + [
            replace(bar, open=bar.open * 2, high=bar.high * 2, low=bar.low * 2, close=bar.close * 2)
            for bar in bars[80:]
        ]
        altered = run_rl(changed, config)
        self.assertEqual(original["checkpoint"], altered["checkpoint"])
        self.assertEqual(original["training"], altered["training"])
        self.assertEqual(original["validation"], altered["validation"])
        checkpoint = json.loads(json.dumps(original["checkpoint"], allow_nan=False))
        observation, _ = ResearchEnv(bars).reset()
        self.assertEqual(
            policy_action(checkpoint, observation),
            policy_action(original["checkpoint"], observation),
        )
        self.assertLess(
            original["splits"]["train"]["end"], original["splits"]["validation"]["start"]
        )
        self.assertLess(
            original["splits"]["validation"]["end"], original["splits"]["test"]["start"]
        )
        test = original["test"]
        self.assertEqual(
            test["backtest"]["equity"][0]["timestamp"], test["benchmark"]["equity"][0]["timestamp"]
        )

    def test_invalid_configuration_and_checkpoint_are_rejected(self):
        for config in (
            {"episodes": 0},
            {"episodes": 2.5},
            {"epsilon": 2},
            {"discount": 1},
            {"train_fraction": 0.99},
        ):
            with self.subTest(config=config), self.assertRaises(ValueError):
                run_rl(market(), config)
        with self.assertRaises(ValueError):
            ResearchEnv(market(11))
        with self.assertRaises(ValueError):
            policy_action({"schema": "executable"}, [0, 0, 1, 0])


if __name__ == "__main__":
    unittest.main()
