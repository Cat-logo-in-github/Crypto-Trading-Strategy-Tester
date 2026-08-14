"""
analysis.engine.metrics.drawdown

Drawdown calculations.

Drawdown measures the decline from a historical
portfolio peak.

These functions operate purely on an equity curve.
"""

from __future__ import annotations

from typing import Sequence

from analysis.engine.metrics.equity import EquityPoint


def drawdowns(
    equity_curve: Sequence[EquityPoint],
) -> list[float]:
    """
    Running drawdown series.

    Returns
    -------
    list[float]

        Decimal drawdowns.

        Example

            [0.0, -0.01, -0.05, -0.02]
    """

    if not equity_curve:
        return []

    peak = equity_curve[0].equity

    result: list[float] = []

    for point in equity_curve:

        peak = max(
            peak,
            point.equity,
        )

        result.append(
            (point.equity - peak)
            / peak
        )

    return result


def max_drawdown(
    equity_curve: Sequence[EquityPoint],
) -> float:
    """
    Maximum portfolio drawdown.

    Returns
    -------
    float

        Decimal value.

        Example

            -0.23

        represents

            -23%
    """

    values = drawdowns(
        equity_curve
    )

    if not values:
        return 0.0

    return min(values)


def peak_equity(
    equity_curve: Sequence[EquityPoint],
) -> float:
    """
    Highest observed portfolio value.
    """

    if not equity_curve:
        return 0.0

    return max(
        point.equity
        for point in equity_curve
    )


def underwater_curve(
    equity_curve: Sequence[EquityPoint],
) -> list[tuple[EquityPoint, float]]:
    """
    Equity paired with drawdown.

    Useful for plotting.
    """

    dd = drawdowns(
        equity_curve
    )

    return list(
        zip(
            equity_curve,
            dd,
        )
    )