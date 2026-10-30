"""Time-aware uncertainty summaries of paired net ledger returns, not edge certification."""

from __future__ import annotations

import math
import random
import statistics


def uncertainty(
    strategy: dict,
    benchmark: dict,
    *,
    samples: int = 300,
    block_bars: int | None = None,
    seed: int = 20261030,
) -> dict:
    if type(samples) is not int or not 100 <= samples <= 1000:
        raise ValueError("Choose 100..1,000 bootstrap samples")
    a = strategy["equity"]
    b = benchmark["equity"]
    if len(a) != len(b) or any(x["timestamp"] != y["timestamp"] for x, y in zip(a, b)):
        raise ValueError("Uncertainty comparison requires matched portfolio valuation times")
    raw = [
        (a[i]["equity"] / a[i - 1]["equity"] - 1) - (b[i]["equity"] / b[i - 1]["equity"] - 1)
        for i in range(1, len(a))
        if a[i - 1]["equity"] > 0 and b[i - 1]["equity"] > 0
    ]
    count = len(raw)
    block = (
        block_bars
        if block_bars is not None
        else min(max(1, count), max(2, min(30, math.ceil(count ** (1 / 3)))))
    )
    if type(block) is not int or not 1 <= block <= max(1, count):
        raise ValueError("Bootstrap block length must fit the history")
    result = {
        "method": "Paired circular moving-block bootstrap of net per-bar strategy-minus-benchmark returns",
        "bars": count,
        "block_bars": block,
        "samples": samples,
        "seed": seed,
        "mean_excess_return_per_bar": statistics.mean(raw) if raw else None,
        "mean_excess_95pct_interval": None,
        "effective_blocks": count / block if block else 0,
        "limitations": [
            "Conditional on this observed period and chosen block length; does not correct data revisions, model misspecification, strategy selection or all multiple testing.",
            "Overlapping labels and a slowly updated feature do not create independent daily evidence. A positive interval is not a probability of future profitability.",
        ],
    }
    if count < 20 or min(row["equity"] for row in a + b) <= 0:
        result["status"] = "Insufficient positive-equity history for this interval"
        return result
    rng = random.Random(seed)
    means = []
    for _ in range(samples):
        values: list[float] = []
        while len(values) < count:
            start = rng.randrange(count)
            values.extend(raw[(start + j) % count] for j in range(block))
        means.append(statistics.mean(values[:count]))
    means.sort()
    result["mean_excess_95pct_interval"] = [
        means[int(0.025 * (samples - 1))],
        means[int(0.975 * (samples - 1))],
    ]
    result["status"] = "Exploratory uncertainty, conditional on supplied data"
    return result
