# Experimental reinforcement learning

`hypothesis_lab.rl` supplies a small working long/cash environment and a bounded tabular Q-learning teaching baseline. This is an **experimental Python workflow**, not a general neural portfolio-training platform. It requires no heavy framework for the bundled example. Its actual executed test evidence is recorded in [implementation status](../IMPLEMENTATION_STATUS.md).

```python
from hypothesis_lab.data import fixtures
from hypothesis_lab.rl import run_rl

bars, _ = fixtures()
result = run_rl(bars, {"episodes": 4, "seed": 42})
print(result["test"]["backtest"]["metrics"])
```

## State, actions and transitions

`ResearchEnv(bars, ExecutionConfig(...))` observes four values after a completed bar: the latest one-bar return, the close/ten-bar-SMA gap, cash weight and long weight. Initial observation is at index 9 after indicator warmup. `reset()` returns `(observation, info)` with initial cash and no position.

Action `0` requests cash; action `1` requests full long spot exposure. An action is decided at the current close, filled at the next open with common fees/slippage/cash constraints, and marked at that next close. Reward is the logarithm of new equity divided by previous equity. The environment uses the common backtest engine rather than an independent fill model.

The base `step(action)` returns `(observation, reward, terminated, info)`. End of the available history terminates the episode; stepping again requires reset. This intentionally small base interface is not itself the five-value Gymnasium API. `result()` returns the accumulated common-engine result after at least one step. It recomputes short episode prefixes to reuse accounting, so it is intentionally unsuitable for large training workloads.

`as_gymnasium(env)` is an optional adapter requiring `pip install -e ".[rl]"`. It exposes discrete two-action and numeric observation spaces and returns `(observation, reward, terminated, False, info)` from step. No artificial time-limit truncation is added. Optional adapter test coverage depends on whether the extra is installed; installing the extra alone does not supply a Stable-Baselines3 training product.

## Training and held-out evaluation

`run_rl` accepts 90 to 2,000 chronological bars and reserves nonoverlapping train/validation/test periods. Defaults are 60%/20%/20%. Each period needs at least 12 bars and starts its own portfolio after ten-bar feature warmup. Evaluation compares the policy with buy-and-hold over that same warmed period, using identical capital/costs.

Training uses a seeded epsilon-greedy tabular Q policy. State buckets discretize one-bar return (threshold 0.001), ten-bar SMA gap (0.005) and long exposure (0.5), for at most 18 states. Unseen states and ties choose cash. Settings include seed, episodes, learning rate, discount, exploration epsilon, split fractions, capital, costs, annualization frequency and interval seconds. Training is bounded to 1–20 episodes and 12,000 transitions. Parameters are fixed before training; neither validation nor test results select them automatically.

The returned numeric JSON checkpoint contains Q values, state/feature definitions, seed and execution settings. `evaluate_policy` and `policy_action` apply that documented inference representation. It is not a pickle and does not execute uploaded model code. Keep schema/type/value validation when importing checkpoints.

Training rewards are reported separately from out-of-sample portfolio metrics. Reusing one history over many episodes can overfit even when training reward rises. This baseline establishes software semantics, not investment merit or a robust learned trading edge. Multi-asset actions, continuous sizing policies, neural agents, automated hyperparameter tuning and a checkpoint-management UI remain future work.

Maintained future integrations include [Gymnasium](https://gymnasium.farama.org/api/env/) and [Stable-Baselines3](https://stable-baselines3.readthedocs.io/en/master/guide/install.html). Keep their dependencies optional and report any CPU/GPU requirements for the specific model rather than assuming accelerated hardware exists.
