"""Run the fixed cross-format software trials without a network connection."""

import argparse
import json
from pathlib import Path

from hypothesis_lab.scenarios import IDS, run_scenarios


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario", action="append", choices=IDS, help="Repeat to choose a subset"
    )
    parser.add_argument(
        "--no-controls", action="store_true", help="Omit the predeclared sensitivities"
    )
    parser.add_argument(
        "--full-records", action="store_true", help="Include full normal experiment records"
    )
    parser.add_argument(
        "--market-csv",
        type=Path,
        help="Optional authorized market CSV; fixtures remain dated 2022–2023",
    )
    parser.add_argument(
        "--market-provenance",
        help="Source, instrument, daily interval, retrieval date and usage rights",
    )
    parser.add_argument(
        "--output", type=Path, help="Write a JSON report only when explicitly requested"
    )
    args = parser.parse_args()
    result = run_scenarios(
        args.scenario,
        include_controls=not args.no_controls,
        include_records=args.full_records,
        market_csv=args.market_csv.read_text(encoding="utf-8-sig") if args.market_csv else None,
        market_provenance=args.market_provenance,
    )
    if args.output:
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
        print(f"Saved {args.output}")
    print(result["data_status"])
    print("Numbers test the software. They do not establish a financial relationship.")
    for item in result["scenarios"]:
        score = item["score"]
        print(
            f"{item['scenario']['title']}: return {score['total_return']:.2%}; "
            f"benchmark {score['benchmark_return']:.2%}; fills {score['trade_count']}; "
            f"replay {item['replay_identical']}; causal prefix {item['prefix_causality']['passed']}"
        )


if __name__ == "__main__":
    main()
