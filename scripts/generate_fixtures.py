"""Regenerate redistributable synthetic offline fixtures (no market API)."""

import csv
import math
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path


def main():
    base = Path(__file__).resolve().parents[1] / "src" / "hypothesis_lab" / "fixtures"
    base.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)
    start = datetime(2023, 1, 1, tzinfo=UTC)
    price = 100.0
    with (base / "market.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
        for index in range(520):
            opened = price * (1 + rng.uniform(-0.004, 0.004))
            price = opened * math.exp(0.0008 + 0.009 * math.sin(index / 18) + rng.gauss(0, 0.009))
            values = [
                opened,
                max(opened, price) * 1.008,
                min(opened, price) * 0.992,
                price,
                1000 + rng.random() * 300,
            ]
            writer.writerow(
                [(start + timedelta(days=index)).isoformat(), *[round(x, 6) for x in values]]
            )
    with (base / "weather.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["observed_at", "available_at", "value", "field", "location"])
        for index in range(520):
            observed = start + timedelta(days=index, hours=6)
            writer.writerow(
                [
                    observed.isoformat(),
                    (observed + timedelta(hours=3)).isoformat(),
                    round(6 + 9 * math.sin(index / 25), 3),
                    "temperature",
                    "Synthetic town",
                ]
            )


if __name__ == "__main__":
    main()
