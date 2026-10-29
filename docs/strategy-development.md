# Rules and Python strategies

Version 0.2 accepts arbitrary mapped external features through [Data discovery](data-sources.md), plus explicit model-output trading policies in [Models & inference](model-inputs.md). Unsupported natural-language ideas open a data-requirements plan; they do not silently become executable trading rules. Public catalog candidates and historical availability assumptions require review before a backtest is meaningful.

A rule strategy produces close-time intents. The simulator fills them at the next bar's open with configured costs. It never fills a close-informed rule at that same close. All supported intents are long-only; the supported model is spot, not derivatives.

## Guided presets

`preset` supports `buy_hold`, `sma_cross`, `momentum`, `mean_reversion`, and `weather`. The SMA preset is a fast-above-slow regime rule: it targets full exposure while above and exits when fast is at or below slow. It is not an intrabar crossover detector. Momentum uses a trailing close return. Mean reversion enters after a trailing loss below -2% and exits when that return is nonnegative.

The weather preset combines a temperature threshold and close above SMA, spending a fee-inclusive cash budget on every qualifying completed bar. There is no exit unless the user adds one. Available temperature values expire after the configured age, measured from observation; missing or stale values make that condition false. A location is required if an event dataset contains several locations.

## Supported natural language

The parser full-matches three forms, with numeric parameters:

```text
Buy and hold Bitcoin
Buy Bitcoin when 20-day SMA is above 50-day SMA
Buy $100 of Bitcoin whenever the temperature in this town falls below 5C, provided Bitcoin is above its 200-day moving average
```

`BTC` and some explicitly implemented wording variants are accepted. Arbitrary prose is not interpreted. An unsupported sentence raises an error so the user can choose a template or edit a supported rule.

## Rule specification

```json
{
  "name": "weather",
  "bar_seconds": 86400,
  "event_max_age_hours": 48,
  "sizing": "cash",
  "amount": 100,
  "entry": {
    "all": [
      {"left": "temperature", "op": "<", "right": 5},
      {"left": "close", "op": ">", "right": "sma_200"}
    ]
  }
}
```

Groups use `all` (AND) or `any` (OR), with bounded nesting and condition counts. Leaves compare `close`, `sma_N`, `momentum_N` or `temperature` to a number or another feature. Operators are `>`, `<`, `>=`, `<=`, `==`. Rolling features need warmup; unavailable values make conditions false. An `exit` rule has priority over `entry`. Target sizing uses `weight` in [0,1]; cash sizing uses positive `amount`. `once` enables one-shot entry intent.

`bar_seconds` must describe the real dataset interval. The app rejects intervals that overlap the next bar. A missing bar is not fabricated; a queued decision waits for the next available open and should be interpreted with the emitted gap warning.

## Python extension

```python
from hypothesis_lab.data import fixtures
from hypothesis_lab.engine import Decision, ExecutionConfig, backtest
from hypothesis_lab.strategies import python_decisions

class EveryThirdBar:
    def decide(self, history):
        if len(history) % 3 == 0:
            return Decision(buy_cash=100)
        return None

bars, _ = fixtures()
decisions = python_decisions(bars, EveryThirdBar())
result = backtest(bars, decisions, ExecutionConfig())
print(result["metrics"])
```

This counter example is a pipeline utility, not a market strategy claim. `history` is an immutable tuple of immutable bars through the current completed bar. The strategy returns a decision or `None`; it does not edit portfolio state or create fills. Keep event joins causal and use explicit availability times when implementing custom features. See [extension API](api/index.md).
