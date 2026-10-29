"""A synthetic arbitrary-input target, probability rule and portable JSON model."""

import json
import math

from hypothesis_lab.data import fixtures
from hypothesis_lab.models import infer_uploaded, run_tabular_model


def main():
    bars, _ = fixtures()
    count = 100.0
    rows = []
    for index in range(len(bars)):
        leading_signal = math.sin(index / 4)
        rows.append({"traffic_count": count, "urban_index": leading_signal})
        # Construct a teaching relationship: today's driver influences tomorrow's count.
        # The driver and current count are already known at today's decision time.
        count += 2 if leading_signal > 0 else -2
    config = {
        "feature_names": ["traffic_count", "urban_index"],
        "target_field": "traffic_count",
        "target_type": "increase",
        "horizon": 1,
        "epochs": 150,
        "l2_candidates": [0.001, 0.01],
        "decision": {
            "comparison": ">",
            "threshold": 0.5,
            "when_true": {"buy_cash": 100},
            "when_false": "hold",
        },
    }
    result = run_tabular_model(bars, rows, config)
    artifact = json.loads(json.dumps(result["model"], allow_nan=False))
    predictions, _ = infer_uploaded(artifact, [rows[-2]])
    print("Synthetic teaching fixture, not market evidence.")
    print("External target:", result["target"])
    print("Held-out diagnostics:", result["test"])
    print("Trading result:", result["backtest"]["metrics"])
    print("Same-cost benchmark:", result["benchmark"]["metrics"])
    print("Safe JSON artifact inference:", predictions)
    print("Discrepancy summary:", result["discrepancy_summary"])


if __name__ == "__main__":
    main()
