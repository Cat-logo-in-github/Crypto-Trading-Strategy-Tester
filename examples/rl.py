"""Run a bounded, experimental offline Q-learning example."""

import argparse
import json
from pathlib import Path

from hypothesis_lab.data import fixtures
from hypothesis_lab.rl import run_rl


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, help="Optional local JSON checkpoint path")
    args = parser.parse_args()
    bars, _ = fixtures()
    result = run_rl(bars)
    print(
        json.dumps(
            {
                "mode": result["mode"],
                "training_transitions": result["training"]["transitions"],
                "validation_strategy": result["validation"]["backtest"]["metrics"],
                "validation_benchmark": result["validation"]["benchmark"]["metrics"],
                "test_strategy": result["test"]["backtest"]["metrics"],
                "test_benchmark": result["test"]["benchmark"]["metrics"],
                "warnings": result["warnings"],
            },
            indent=2,
            allow_nan=False,
        )
    )
    if args.checkpoint:
        args.checkpoint.write_text(
            json.dumps(result["checkpoint"], indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
        print(f"Saved JSON checkpoint to {args.checkpoint}")


if __name__ == "__main__":
    main()
