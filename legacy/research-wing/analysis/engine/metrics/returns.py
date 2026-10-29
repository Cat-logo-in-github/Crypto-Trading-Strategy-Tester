"""
analysis.engine.metrics.returns

Portfolio return calculations.

These functions operate on an equity curve and provide
basic return statistics.

They are pure functions:
- no portfolio access
- no market access
- no backtester dependency
"""

from __future__ import annotations

from typing import Sequence

from analysis.engine.metrics.equity import EquityPoint


def total_return(
    equity_curve: Sequence[EquityPoint],
) -> float:
    """
    Total portfolio return.

    Returns
    -------
    float
        Decimal return.

        Example:

            0.25

        represents

            +25%
    """

    if len(equity_curve) < 2:
        return 0.0

    start = equity_curve[0].equity
    end = equity_curve[-1].equity

    if start <= 0:
        raise ValueError(
            "Initial equity must be positive."
        )

    return (end - start) / start


def cumulative_returns(
    equity_curve: Sequence[EquityPoint],
) -> list[float]:
    """
    Cumulative return at each timestep.

    Example:

        [0.00, 0.01, 0.03, 0.02]
    """

    if not equity_curve:
        return []

    start = equity_curve[0].equity

    if start <= 0:
        raise ValueError(
            "Initial equity must be positive."
        )

    return [
        (point.equity - start) / start
        for point in equity_curve
    ]


def periodic_returns(
    equity_curve: Sequence[EquityPoint],
) -> list[float]:
    """
    Return between consecutive observations.

    Example

        Equity

            100
            101
            99

        Returns

            0.01
            -0.0198
    """

    if len(equity_curve) < 2:
        return []

    returns: list[float] = []

    previous = equity_curve[0].equity

    for point in equity_curve[1:]:

        if previous <= 0:
            raise ValueError(
                "Equity must remain positive."
            )

        returns.append(
            (point.equity - previous)
            / previous
        )

        previous = point.equity

    return returns