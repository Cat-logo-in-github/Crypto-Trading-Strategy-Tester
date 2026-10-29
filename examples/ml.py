"""Run a generated offline experiment using a safe JSON model.

From the repository root after installation: python examples/ml.py
"""

import json
import math
from datetime import UTC, datetime, timedelta

from hypothesis_lab.data import Bar
from hypothesis_lab.ml import run_ml


def main():
    bars = []
    previous = 100.0
    for i in range(180):
        close = 100 + i * 0.1 + 4 * math.sin(i / 6) + math.sin(i / 2)
        bars.append(
            Bar(
                timestamp=datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=i),
                open=previous,
                high=max(previous, close) + 1,
                low=min(previous, close) - 1,
                close=close,
                volume=1000 + 100 * math.cos(i / 3),
            )
        )
        previous = close
    result = run_ml(bars)
    print(
        json.dumps(
            {
                "selected_alpha": result["search"]["selected_alpha"],
                "test_prediction_metrics": result["test"],
                "strategy_metrics": result["backtest"]["metrics"],
                "benchmark_metrics": result["benchmark"]["metrics"],
            },
            indent=2,
            allow_nan=False,
        )
    )
    print("The full result contains result['model'], a JSON-safe inference artifact.")


if __name__ == "__main__":
    main()
