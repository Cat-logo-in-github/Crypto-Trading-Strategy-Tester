"""Run a causal Python strategy without editing the execution engine."""

from hypothesis_lab.data import fixtures
from hypothesis_lab.engine import Decision, backtest, benchmark
from hypothesis_lab.strategies import python_decisions


class SimpleTrend:
    def decide(self, history):
        if len(history) < 20:
            return None
        average = sum(bar.close for bar in history[-20:]) / 20
        return Decision(target_weight=0.5 if history[-1].close > average else 0)


if __name__ == "__main__":
    bars, _ = fixtures()
    result = backtest(bars, python_decisions(bars, SimpleTrend()))
    print("Synthetic fixture strategy:", result["metrics"])
    print("Same-cost benchmark:", benchmark(bars)["metrics"])
