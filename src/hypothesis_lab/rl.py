"""Experimental, bounded portfolio environment and a tiny tabular Q baseline."""

from __future__ import annotations

import math
import random
from collections.abc import Mapping
from dataclasses import asdict
from datetime import timedelta
from typing import Any

from .data import Bar, validate_bars
from .engine import Decision, ExecutionConfig, backtest, benchmark

CHECKPOINT_SCHEMA = "hypothesis-lab/tabular-q-v1"


class ResearchEnv:
    """A single-instrument long/cash environment with next-open execution.

    Observation at close t: last return, ten-bar SMA gap, cash weight, long
    weight. Action 0 requests cash; action 1 requests 100% long. A transition
    fills at open t+1, marks at close t+1, and rewards log equity change.
    The engine recomputes the short episode prefix to share all fill accounting.
    """

    def __init__(self, bars: list[Bar], config: ExecutionConfig | None = None):
        validate_bars(bars)
        if not 12 <= len(bars) <= 2000:
            raise ValueError("RL episodes require 12 to 2,000 bars")
        self.bars = list(bars)
        self.config = config or ExecutionConfig()
        if any(
            (b.timestamp - a.timestamp).total_seconds() < self.config.bar_seconds
            for a, b in zip(bars, bars[1:])
        ):
            raise ValueError("Configured bar duration overlaps the next bar")
        self.reset()

    def reset(self) -> tuple[list[float], dict[str, Any]]:
        self.index = 9
        self.decisions: list[Decision | None] = []
        self.equity = self.config.initial_cash
        self.cash = self.config.initial_cash
        self.units = 0.0
        self.terminated = False
        self._result: dict[str, Any] | None = None
        return self._observation(), self._info()

    def _observation(self) -> list[float]:
        current = self.bars[self.index]
        average = sum(bar.close for bar in self.bars[self.index - 9 : self.index + 1]) / 10
        observation = [
            current.close / self.bars[self.index - 1].close - 1,
            current.close / average - 1,
            self.cash / self.equity,
            self.units * current.close / self.equity,
        ]
        if not all(math.isfinite(value) for value in observation):
            raise ValueError("RL observations exceed finite numeric limits")
        return observation

    def _info(self) -> dict[str, Any]:
        return {
            "bar_index": self.index,
            "bar_open_timestamp": self.bars[self.index].timestamp.isoformat(),
            "decision_at": (
                self.bars[self.index].timestamp + timedelta(seconds=self.config.bar_seconds)
            ).isoformat(),
            "equity": self.equity,
            "cash": self.cash,
            "units": self.units,
        }

    def step(self, action: int) -> tuple[list[float], float, bool, dict[str, Any]]:
        if self.terminated:
            raise ValueError("Episode ended; call reset before taking another action")
        if isinstance(action, bool) or not isinstance(action, int) or action not in (0, 1):
            raise ValueError("Action must be integer 0 (cash) or 1 (long)")
        previous_equity = self.equity
        self.decisions.append(Decision(target_weight=float(action)))
        self.index += 1
        self._result = backtest(self.bars[9 : self.index + 1], [*self.decisions, None], self.config)
        portfolio = self._result["equity"][-1]
        self.equity = portfolio["equity"]
        self.cash = portfolio["cash"]
        self.units = portfolio["units"]
        self.terminated = self.index == len(self.bars) - 1
        reward = math.log(self.equity / previous_equity)
        return self._observation(), reward, self.terminated, self._info()

    def result(self) -> dict[str, Any]:
        if self._result is None:
            raise ValueError("Take at least one step before requesting a backtest result")
        return self._result


def _state(observation: list[float]) -> str:
    change, gap, _, position = observation

    def bucket(value: float, threshold: float) -> int:
        return -1 if value < -threshold else 1 if value > threshold else 0

    return f"{bucket(change, 0.001)}:{bucket(gap, 0.005)}:{int(position > 0.5)}"


def policy_action(checkpoint: Mapping[str, Any], observation: list[float]) -> int:
    """Evaluate numeric JSON Q values; unseen states and ties choose cash."""
    if checkpoint.get("schema") != CHECKPOINT_SCHEMA:
        raise ValueError("Unsupported RL checkpoint schema")
    table = checkpoint.get("q_values")
    if not isinstance(table, dict) or len(table) > 18:
        raise ValueError("Invalid Q table")
    values = table.get(_state(observation), [0.0, 0.0])
    if not isinstance(values, list) or len(values) != 2:
        raise ValueError("Q states must contain exactly two action values")
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
        for value in values
    ):
        raise ValueError("Q values must be finite numbers")
    return int(values[1] > values[0])


def evaluate_policy(
    bars: list[Bar], checkpoint: Mapping[str, Any], config: ExecutionConfig | None = None
) -> dict[str, Any]:
    env = ResearchEnv(bars, config)
    observation, _ = env.reset()
    rewards = []
    done = False
    while not done:
        observation, reward, done, _ = env.step(policy_action(checkpoint, observation))
        rewards.append(reward)
    return {
        "reward_sum": sum(rewards),
        "steps": len(rewards),
        "backtest": env.result(),
        "benchmark": benchmark(bars[9:], env.config),
    }


def run_rl(bars: list[Bar], config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Fit one fixed small tabular policy, then report untouched later periods.

    No validation or test observations, rewards, or returns choose parameters.
    This is a teaching baseline; repeated training on one history can overfit.
    """
    validate_bars(bars)
    if not 90 <= len(bars) <= 2000:
        raise ValueError("RL research requires 90 to 2,000 chronological bars")
    settings = dict(config or {})

    def number(name: str, default: float) -> float:
        value = settings.get(name, default)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"{name} must be a finite number")
        return float(value)

    episodes = number("episodes", 8)
    seed = number("seed", 42)
    if not episodes.is_integer() or not 1 <= episodes <= 20:
        raise ValueError("episodes must be an integer from 1 to 20")
    if not seed.is_integer() or not 0 <= seed <= 2**31 - 1:
        raise ValueError("seed must be a nonnegative 32-bit integer")
    learning_rate = number("learning_rate", 0.15)
    discount = number("discount", 0.95)
    epsilon = number("epsilon", 0.2)
    if not 0 < learning_rate <= 1 or not 0 <= discount < 1 or not 0 <= epsilon <= 1:
        raise ValueError("learning_rate in (0,1], discount in [0,1), epsilon in [0,1] required")
    train_fraction = number("train_fraction", 0.6)
    validation_fraction = number("validation_fraction", 0.2)
    if (
        not 0 < train_fraction < 1
        or not 0 < validation_fraction < 1
        or train_fraction + validation_fraction >= 1
    ):
        raise ValueError("Choose positive chronological fractions with a reserved test period")
    train_end = int(len(bars) * train_fraction)
    validation_end = int(len(bars) * (train_fraction + validation_fraction))
    periods = {
        "train": bars[:train_end],
        "validation": bars[train_end:validation_end],
        "test": bars[validation_end:],
    }
    if any(len(period) < 12 for period in periods.values()):
        raise ValueError("Each chronological RL period must contain at least twelve bars")
    transitions = (len(periods["train"]) - 10) * int(episodes)
    if transitions > 12000:
        raise ValueError("Training budget exceeds 12,000 transitions; reduce episodes or bars")
    execution = ExecutionConfig(
        initial_cash=number("initial_cash", 10000),
        fee_bps=number("fee_bps", 10),
        slippage_bps=number("slippage_bps", 5),
        periods_per_year=number("periods_per_year", 365),
        bar_seconds=number("bar_seconds", 86400),
        fixed_fee=number("fixed_fee", 0),
        spread_bps=number("spread_bps", 0),
        data_delay_ms=number("data_delay_ms", 0),
        latency_ms=number("latency_ms", 0),
    )
    rng = random.Random(int(seed))
    table: dict[str, list[float]] = {}
    checkpoint: dict[str, Any] = {"schema": CHECKPOINT_SCHEMA, "q_values": table}
    training_rewards = []
    for _ in range(int(episodes)):
        env = ResearchEnv(periods["train"], execution)
        observation, _ = env.reset()
        done, total_reward = False, 0.0
        while not done:
            state = _state(observation)
            values = table.setdefault(state, [0.0, 0.0])
            action = (
                rng.randrange(2)
                if rng.random() < epsilon
                else policy_action(checkpoint, observation)
            )
            next_observation, reward, done, _ = env.step(action)
            next_values = table.get(_state(next_observation), [0.0, 0.0])
            target = reward + (discount * max(next_values) if not done else 0.0)
            values[action] += learning_rate * (target - values[action])
            observation = next_observation
            total_reward += reward
        training_rewards.append(total_reward)
    checkpoint.update(
        {
            "seed": int(seed),
            "episodes": int(episodes),
            "learning_rate": learning_rate,
            "discount": discount,
            "epsilon": epsilon,
            "observation": ["return_1", "sma_gap_10", "cash_weight", "long_weight"],
            "state_bins": {"return_1": 0.001, "sma_gap_10": 0.005, "long_weight": 0.5},
            "execution": asdict(execution),
        }
    )
    return {
        "mode": "rl-experimental",
        "checkpoint": checkpoint,
        "configuration": {
            "episodes": int(episodes),
            "seed": int(seed),
            "learning_rate": learning_rate,
            "discount": discount,
            "epsilon": epsilon,
            "train_fraction": train_fraction,
            "validation_fraction": validation_fraction,
            **asdict(execution),
        },
        "splits": {
            name: {
                "start": period[0].timestamp.isoformat(),
                "end": period[-1].timestamp.isoformat(),
                "bars": len(period),
                "evaluation_start": period[9].timestamp.isoformat(),
            }
            for name, period in periods.items()
        },
        "training": {"episode_rewards": training_rewards, "transitions": transitions},
        "validation": evaluate_policy(periods["validation"], checkpoint, execution),
        "test": evaluate_policy(periods["test"], checkpoint, execution),
        "warnings": [
            "Experimental tabular Q teaching baseline; training reward is not investment return.",
            "No model selection uses validation or test periods. Parameters are fixed before training.",
            "Repeated episodes reuse one history and can overfit. No trading edge is claimed.",
            "Single-instrument long/cash actions only; no leverage, shorting, or real-money orders.",
            "Prefix engine recomputation is deliberately simple and limited to small experiments.",
        ],
    }


def as_gymnasium(environment: ResearchEnv):
    """Create an optional Gymnasium adapter; base research needs no Gym dependency."""
    try:
        import gymnasium as gym
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("Install hypothesis-lab[rl] to use the Gymnasium adapter") from exc

    class Adapter(gym.Env):
        metadata: dict[str, list[str]] = {"render_modes": []}

        def __init__(self):
            self.action_space = gym.spaces.Discrete(2)
            self.observation_space = gym.spaces.Box(
                low=np.array([-np.inf, -np.inf, 0.0, 0.0], dtype=np.float64),
                high=np.array([np.inf, np.inf, 1.0, 1.0], dtype=np.float64),
                dtype=np.float64,
            )

        def reset(self, *, seed=None, options=None):
            super().reset(seed=seed)
            observation, info = environment.reset()
            return np.array(observation, dtype=np.float64), info

        def step(self, action):
            if isinstance(action, bool) or not self.action_space.contains(action):
                raise ValueError("Action must belong to the Discrete(2) action space")
            observation, reward, done, info = environment.step(int(action))
            return np.array(observation, dtype=np.float64), reward, done, False, info

    return Adapter()
